"""Command line entry point.

``aicli "prompt"`` is shorthand for ``aicli run "prompt"``. The answer goes to
stdout; cost estimates, fallback notices and errors go to stderr, so
``aicli "..." --format json | jq`` always sees clean output.

Exit codes: 0 ok, 1 every provider failed, 2 usage or config error.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

from . import __version__, config, pricing
from .providers import Completion, ProviderError
from .router import AllProvidersFailed, Router, Target
from .storage import Run, Store

COMMANDS = ("run", "chat", "list", "history", "search", "stats", "config")
QUIT_WORDS = (":quit", ":q", ":exit")


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _store() -> Store:
    return Store(config.home() / "history.db")


def _cost(router: Router, target: Target, inp: int, out: int) -> float | None:
    price = pricing.price_of(target.model, router.provider_type(target), router.config.prices)
    return pricing.cost(price, inp, out)


def _render(fmt: str, c: Completion, target: Target, cost: float | None,
            fell_back_from: Target | None) -> str:
    if fmt == "json":
        return json.dumps({
            "text": c.text, "provider": target.provider, "model": c.model,
            "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
            "cost_usd": cost, "latency_ms": c.latency_ms, "stop_reason": c.stop_reason,
            "fallback_from": str(fell_back_from) if fell_back_from else None,
        }, indent=2)
    if fmt == "markdown":
        meta = (f"*{target} · {c.input_tokens}→{c.output_tokens} tokens · "
                f"{pricing.fmt_usd(cost)} · {c.latency_ms} ms*")
        return f"{c.text}\n\n---\n{meta}"
    return c.text


def _ask(router: Router, store: Store, messages: list[dict[str, str]], args,
         session: str | None) -> tuple[Completion, Target, float | None, Target | None]:
    """One routed call, with the estimate before and the record after."""
    prompt = messages[-1]["content"]
    first = router.candidates(args.model)[0]
    if not args.quiet:
        inp = pricing.estimate_tokens(" ".join(m["content"] for m in messages))
        ceiling = _cost(router, first, inp, args.max_tokens or router.config.max_tokens)
        _err(f"→ {first}  ~{inp} input tokens, est. ≤ {pricing.fmt_usd(ceiling)}")

    def on_fallback(target: Target, why: str) -> None:
        _err(f"! {target} failed: {why}")
        if not args.no_save:
            store.add(Run(provider=target.provider, model=target.model, prompt=prompt,
                          response=None, status="error", error=why, session=session))

    result = router.complete(messages, args.model, args.max_tokens, args.system, on_fallback)
    c, target = result.completion, result.target
    cost = _cost(router, target, c.input_tokens, c.output_tokens)
    fb = result.fell_back_from
    if fb and not args.quiet:
        _err(f"↪ fell back from {fb} to {target}")
    if not args.no_save:
        store.add(Run(provider=target.provider, model=target.model, prompt=prompt,
                      response=c.text, input_tokens=c.input_tokens,
                      output_tokens=c.output_tokens, cost_usd=cost, latency_ms=c.latency_ms,
                      fallback_from=str(fb) if fb else None, session=session))
    if not args.quiet:
        _err(f"✓ {target}  {c.input_tokens}→{c.output_tokens} tokens, "
             f"{pricing.fmt_usd(cost)}, {c.latency_ms} ms")
    return c, target, cost, fb


def cmd_run(args, cfg: config.Config) -> int:
    prompt = " ".join(args.prompt) if args.prompt else ""
    if prompt == "-" or (not prompt and not sys.stdin.isatty()):
        prompt = sys.stdin.read()
    if not prompt.strip():
        _err("no prompt given (pass text, or pipe it on stdin)")
        return 2
    router, store = Router(cfg), _store()
    try:
        c, target, cost, fb = _ask(router, store, [{"role": "user", "content": prompt}],
                                   args, session=None)
    finally:
        store.close()
    print(_render(args.format or cfg.format, c, target, cost, fb))
    return 0


def cmd_chat(args, cfg: config.Config) -> int:
    router, store = Router(cfg), _store()
    session = uuid.uuid4().hex[:8]
    messages: list[dict[str, str]] = []
    total: float | None = 0.0
    _err(f"chat with {router.resolve(args.model)} — session {session}; "
         f"{' / '.join(QUIT_WORDS)} to leave")
    try:
        while True:
            try:
                line = input("you> ")
            except EOFError:
                break
            if line.strip() in QUIT_WORDS:
                break
            if not line.strip():
                continue
            messages.append({"role": "user", "content": line})
            try:
                c, target, cost, _ = _ask(router, store, messages, args, session)
            except AllProvidersFailed as exc:
                _err(str(exc))
                messages.pop()
                continue
            messages.append({"role": "assistant", "content": c.text})
            total = None if total is None or cost is None else total + cost
            print(f"{target.model}> {c.text}")
    finally:
        store.close()
    _err(f"session {session} total: {pricing.fmt_usd(total)}")
    return 0


def cmd_list(args, cfg: config.Config) -> int:
    router = Router(cfg)
    rows: list[dict[str, Any]] = []
    for name in cfg.providers:
        provider = router.provider(name)
        ok, why = provider.available()
        row: dict[str, Any] = {"provider": name, "type": provider.type, "available": ok,
                               "detail": why}
        if args.what == "models":
            try:
                row["models"] = provider.list_models() if ok else []
            except ProviderError as exc:
                row["models"], row["detail"] = [], str(exc)
        rows.append(row)
    if args.format == "json":
        print(json.dumps(rows, indent=2))
        return 0
    for row in rows:
        mark = "✓" if row["available"] else "✗"
        print(f"{mark} {row['provider']:<12} {row['type']:<10} {row['detail']}")
        for model in row.get("models", []):
            print(f"    {row['provider']}/{model}")
    if args.what == "models" and cfg.aliases:
        print("\naliases:")
        for alias, target in cfg.aliases.items():
            print(f"    {alias:<12} → {target}")
    return 0


def _print_runs(rows: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(rows, indent=2))
        return
    for r in rows:
        head = f"#{r['id']} {r['created_at']} {r['provider']}/{r['model']}"
        if r["status"] != "ok":
            head += f" [error: {r['error']}]"
        if fmt == "markdown":
            print(f"## {head}\n\n**Prompt**\n\n{r['prompt']}\n\n**Response**\n\n"
                  f"{r['response'] or '_none_'}\n")
        else:
            snippet = (r["response"] or "").replace("\n", " ")
            print(f"{head}\n  > {r['prompt'][:100]}\n  < {snippet[:100]}")


def cmd_history(args, cfg: config.Config) -> int:
    store = _store()
    try:
        _print_runs(store.history(args.limit, args.model), args.format)
    finally:
        store.close()
    return 0


def cmd_search(args, cfg: config.Config) -> int:
    store = _store()
    try:
        rows = store.search(" ".join(args.query), args.limit)
    finally:
        store.close()
    if not rows:
        _err("no matches")
        return 0
    _print_runs(rows, args.format)
    return 0


def cmd_stats(args, cfg: config.Config) -> int:
    store = _store()
    try:
        rows = store.stats(args.session)
    finally:
        store.close()
    if args.format == "json":
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no calls recorded yet")
        return 0
    print(f"{'model':<36} {'calls':>5} {'err':>4} {'in':>8} {'out':>8} {'avg ms':>7}  cost")
    total = 0.0
    for r in rows:
        total += r["cost_usd"] or 0
        if r["unpriced"]:
            cost = "partly unpriced"
        elif r["cost_usd"] is None:
            cost = "—"  # only failed calls: nothing was billed
        else:
            cost = pricing.fmt_usd(r["cost_usd"])
        print(f"{r['provider'] + '/' + r['model']:<36} {r['calls']:>5} {r['errors']:>4} "
              f"{r['input_tokens'] or 0:>8} {r['output_tokens'] or 0:>8} "
              f"{r['avg_latency_ms'] or 0:>7}  {cost}")
    print(f"\ntotal (priced calls): ${total:.4f}   prices as of {pricing.PRICES_AS_OF}")
    return 0


def cmd_config(args, cfg: config.Config) -> int:
    if args.action == "init":
        print(f"wrote {config.init(force=args.force)}")
    elif args.action == "path":
        print(config.config_path())
    elif args.action == "show":
        path = config.config_path()
        print(path.read_text() if path.exists() else
              f"# {path} does not exist; these are the built-in defaults\n"
              + config.DEFAULT_CONFIG)
    elif args.action == "detect":
        return cmd_list(argparse.Namespace(what="providers", format="text"), cfg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aicli", description="One command, any model.")
    p.add_argument("--version", action="version", version=f"aicli {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def model_opts(sp):
        sp.add_argument("-m", "--model", help="provider/model or alias (default from config)")
        sp.add_argument("--max-tokens", type=int)
        sp.add_argument("-s", "--system", help="system prompt")
        sp.add_argument("-q", "--quiet", action="store_true", help="no cost lines on stderr")
        sp.add_argument("--no-save", action="store_true", help="do not record in history")

    run = sub.add_parser("run", help="send one prompt (the default command)")
    run.add_argument("prompt", nargs="*", help="prompt text; '-' or a pipe reads stdin")
    run.add_argument("-f", "--format", choices=config.VALID_FORMATS)
    model_opts(run)
    run.set_defaults(fn=cmd_run)

    chat = sub.add_parser("chat", help="multi-turn conversation")
    model_opts(chat)
    chat.set_defaults(fn=cmd_chat)

    ls = sub.add_parser("list", help="providers and models")
    ls.add_argument("what", choices=("providers", "models"))
    ls.add_argument("-f", "--format", choices=("text", "json"), default="text")
    ls.set_defaults(fn=cmd_list)

    for name, fn, help_ in (("history", cmd_history, "recent prompts and responses"),
                            ("search", cmd_search, "full-text search over history")):
        sp = sub.add_parser(name, help=help_)
        if name == "search":
            sp.add_argument("query", nargs="+")
        else:
            sp.add_argument("-m", "--model")
        sp.add_argument("-n", "--limit", type=int, default=20)
        sp.add_argument("-f", "--format", choices=config.VALID_FORMATS, default="text")
        sp.set_defaults(fn=fn)

    st = sub.add_parser("stats", help="calls, tokens, latency and cost per model")
    st.add_argument("--session")
    st.add_argument("-f", "--format", choices=("text", "json"), default="text")
    st.set_defaults(fn=cmd_stats)

    cf = sub.add_parser("config", help="init | show | path | detect")
    cf.add_argument("action", choices=("init", "show", "path", "detect"))
    cf.add_argument("--force", action="store_true")
    cf.set_defaults(fn=cmd_config)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `aicli "prompt"` and `aicli -m x "prompt"` both mean `aicli run ...`.
    run_flags = ("-m", "--model", "-f", "--format", "-s", "--system", "-q", "--quiet")
    is_prompt = bool(argv) and argv[0] not in COMMANDS and not argv[0].startswith("-")
    if is_prompt or (argv and argv[0] in run_flags):
        argv.insert(0, "run")
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args, config.load())
    except config.ConfigError as exc:
        _err(f"config error: {exc}")
        return 2
    except AllProvidersFailed as exc:
        _err(str(exc))
        return 1
