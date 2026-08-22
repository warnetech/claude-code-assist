# Operations

What keeps a deployed integration running, as opposed to making it smarter.
Most of this is adapted from a production system that had already paid for the
lessons — see [Provenance](#provenance).

## Rate limiting before retrying

`with_retry` reacts to a 429 that has already cost a round trip. A token bucket
prevents it. Three things a retry loop cannot address:

- **Retries make the problem worse.** The burst that tripped the limit is
  followed by retries arriving in the same window.
- **Shared quota.** An eval sweep and a production agent on one key compete. A
  bucket per key lets the production path keep working while the sweep waits.
- **Cost control is not rate control.** `Budget.max_usd` stops a run that has
  already spent the money.

```python
from llmforge import with_rate_limit

provider = with_rate_limit(
    AnthropicProvider(),
    requests_per_minute=120,
    key=lambda request: request.model,   # a bucket per model
)
```

`block=False` raises `RateLimitExceeded` instead of waiting — the right choice
on an interactive path, where a caller would rather be told to come back.

### Canonical wrapper order

The wrappers compose, and the order changes the behaviour. Pick it deliberately:

```python
TracedProvider(                 # outermost: sees everything, including waits
    with_retry(                 # retries what still fails
        with_rate_limit(        # paces before the call is made
            RecordingProvider(  # innermost: replays without spending
                AnthropicProvider()))))
```

Rate limiting *inside* retry means a retry storm is also paced. Recording
*innermost* means a replayed call costs neither a token nor a request. Getting
this backwards is silent — everything still works, it just stops helping.

## `doctor`: report, never raise

Half the support burden of any toolkit is "it doesn't work" with no detail.

```bash
llmforge doctor           # offline; exits 1 if anything is failing
llmforge doctor --live    # adds one real call on the cheapest model
llmforge doctor --json    # for CI
```

Three rules, and they are the whole design:

1. **Every check returns `{"ok": bool, ...}`.** Machine-readable first, prose
   second. A human reads `render_doctor()`; CI reads the dict.
2. **No check raises.** `doctor()` wraps each one, so a bug in a single check
   cannot take down the report — which is exactly when you need the other ten
   findings.
3. **A missing credential is a finding, not a crash.** That is the common case
   for running this at all.

The most valuable check is `assurance_gates`: it feeds known-bad input to every
gate and fails if any of them *stopped firing*. A gate that has silently gone
quiet is worse than no gate, because it reports clean and provides cover.

## Retention

Traces and audit chains grow without bound. Left alone they become the reason
someone disables tracing, and then the run you most wanted a record of is the
one where the disk was full.

Age decides the tier; the tier decides the fidelity:

| Tier | Default window | What survives |
|---|---|---|
| hot | ≤ 3 days | everything |
| warm | ≤ 30 days | name, kind, attrs, error, duration |
| cold | ≤ 365 days | name, kind, error |
| gone | beyond | deleted |

```bash
llmforge retention .llmforge/trace.jsonl --dry-run     # always start here
llmforge retention .llmforge/trace.jsonl --archive .llmforge/archive.jsonl
```

Two rules make it safe to run unattended:

- **An audit chain is never rewritten, only archived.** Editing an entry to
  compact it changes its digest and breaks the chain from that point forward —
  destroying the one property the chain exists to provide. `sweep_audit`
  therefore *rejects* a tier that declares `keep_fields`, and `AUDIT_TIERS` has
  no horizon by default. An audit trail is evidence.
- **A record that cannot be dated is kept.** Guessing an age and then deleting
  on the guess is the one outcome worse than keeping too much.

## Provenance

The patterns above are adapted from
[`tewartech-node/claude-command-cli`](https://github.com/tewartech-node/claude-command-cli),
a production CLI → server → control-plane system. What transferred, and what
changed on the way:

| Taken from | Became | What changed |
|---|---|---|
| per-principal `RateLimiter` in the server middleware | `llmforge.limits` | moved to the *client* side, where an SDK integration needs it; keyed by a callable so one process can hold several lanes |
| `warnetech_cli/diagnostics.py` | `llmforge.doctor` | same three rules verbatim; checks are about the library rather than a server |
| hot/warm/ghost `RetentionPolicy` | `llmforge.retention` | reduced to what a library can honestly promise, plus the audit-chain carve-out |
| the middleware chain's documented ordering | canonical wrapper order, above | the *discipline* of writing the order down and saying why |
| `tests/security/test_envelope_interop.py` | `fixtures/assurance-parity.json` | see below — the most important one |

### The parity fixtures

That project's envelope module carries this line:

> *"New encryption: extend `warnetech_envelope` — never add a second
> implementation; **that is what broke the CLI/Worker channel**."*

The assurance gates here are exactly that shape: one contract, two
implementations. When the fixtures were first written they immediately caught
real divergence — on eight probe inputs the Python and TypeScript gates
disagreed on six:

| input | Python (before) | TypeScript (before) |
|---|---|---|
| `class HandlerBase:` | miss | flagged |
| `export abstract class AbstractHandlerBase {}` | miss | flagged |
| `def make_handler_factory():` | miss | miss |
| `function makeHandlerFactory() {}` | miss | flagged |
| `except Exception: pass` | flagged | miss |
| `catch {}` | miss | flagged |
| `# TODO` | flagged | miss |
| `// TODO` | miss | flagged |

Each implementation only recognised its own host language, which meant a Python
harness reviewing a TypeScript diff reported clean on code it had never
understood. The two also used different tab widths (4 vs 2), so identical files
measured different nesting depths, and different comment prefixes, so identical
files measured different line counts.

All three are now pinned by `fixtures/assurance-parity.json`, which both test
suites load. Assertions are on the machine-readable `Violation.code`, never on
prose — messages get reworded, codes do not. **Adding a finding means adding it
to the fixtures first, then to both implementations.**

### What was deliberately not taken

- The three-layer CLI → server → repo architecture. llmforge is a library.
- The AES-256-GCM envelope. There is no wire protocol here to secure.
- The control-plane scoring, anomaly and signature engines. Those solve
  network-defence problems, not codebase-integration ones.

One idea from the learning engine is worth flagging as *not yet taken*: its
rule that a payload matching three weak signatures must **reinforce those, not
mint a fourth**. `labs/05-memory`'s `LessonStore` merges on an exact
claim-string match, which is the naive version of the same problem and will
duplicate near-identical lessons. That is a real known gap.
