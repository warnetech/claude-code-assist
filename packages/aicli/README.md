# aicli — CLI-to-AI Command Center

**One command, any model.** A local-first CLI for Claude, OpenAI and Ollama with
logged fallback, cost estimates, and a searchable local history.

The product plan is in [`CLI-AI-Command-Center-PRD.md`](CLI-AI-Command-Center-PRD.md).
This repository implements **Phase 1 (the quick win)**. What shipped and what is
deferred is listed below.

```bash
pip install -e ".[dev]"
aicli "hello" -m echo/echo        # offline: no keys, no Ollama needed
aicli config init                 # writes ~/.aicli/config.toml
aicli list providers              # what is reachable right now, and why not
```

## Use

```bash
aicli "Explain quantum computing"                    # default model (local Ollama)
aicli "Explain quantum computing" -m sonnet          # alias → anthropic/claude-sonnet-5
aicli "Explain quantum computing" -m openai/gpt-4o -f json | jq .cost_usd
git diff | aicli -m opus -s "Review this diff" -     # prompt from stdin
aicli chat -m local/mistral                          # multi-turn; :quit to leave
aicli history -n 5 -f markdown > notes.md            # export
aicli search quantum                                 # full-text search (SQLite FTS5)
aicli stats                                          # calls, tokens, latency, cost per model
aicli list models
```

The answer goes to **stdout**. The cost estimate, fallback notices and errors go to
**stderr**, so piping always sees clean output. Exit codes: `0` ok, `1` every
provider failed, `2` usage or config error.

## Configuration

`~/.aicli/config.toml` (override the directory with `AICLI_HOME`). Keys are never
stored in the file. Each provider names the environment variable that holds its key:

```toml
default_model = "local/llama3.2"   # local-first
fallback = []                      # e.g. ["sonnet"]; empty = never reroute silently

[providers.local]
type = "ollama"
base_url = "http://localhost:11434"

[providers.anthropic]
type = "anthropic"
api_key_env = "ANTHROPIC_API_KEY"

[aliases]
sonnet = "anthropic/claude-sonnet-5"

[prices]                           # USD per 1M tokens, overrides the built-in table
"gpt-4o" = [2.50, 10.00]
```

Model strings resolve in this order: an alias, then `provider/model`, then a bare
name with an obvious owner (`claude-*` → anthropic, `gpt-*` → openai). Provider
types are `anthropic`, `openai` (any OpenAI-compatible endpoint via `base_url`),
`ollama` and `fake` (an offline echo).

## Phase 1 status

| PRD Phase 1 feature | Status |
|---|---|
| Unified prompt execution across Claude / OpenAI / Ollama | ✅ |
| Provider detection and fallback, with fallback logged | ✅ stderr + history |
| Config file | ✅ TOML (PRD said YAML; see decisions) |
| SQLite conversation storage, search, export | ✅ FTS5 with a LIKE fallback |
| Cost estimate before the call, actual cost after, totals | ✅ `stats`, chat session total |
| Text / JSON / Markdown output | ✅ |
| `list models`, `list providers`, `stats` | ✅ |
| Multi-turn chat (PRD Phase 1.5) | ✅ basic, in memory per session |
| PyPI release, GitHub Actions template | ⏳ Phase 1.5 |
| Tool calling, MCP, batch, cost-aware routing, templates | ⏳ Phase 2 |

## Development

```bash
pip install -e ".[dev]"
pytest -q          # fully offline: HTTP is stubbed, the echo provider stands in for models
ruff check src tests
```

See [`docs/decisions.md`](docs/decisions.md) for where this build departs from the PRD, and why.
