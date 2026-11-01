# Decisions: where Phase 1 departs from the PRD

The PRD's stack table proposed Typer + Rich + Pydantic + YAML + LiteLLM + httpx.
Phase 1 ships on the **standard library only**. Each departure can be reversed
once a later phase needs what the dependency adds.

| PRD | Phase 1 | Why |
|---|---|---|
| LiteLLM | Three small HTTP providers (`providers.py`) | The PRD's own risk table says to "abstract behind our own provider interface". Phase 1 needs three providers, not 100. LiteLLM can come back later as one more provider type behind the same interface. |
| Typer + Rich | argparse | No dependencies, and the install is instant. Rich output is a cosmetic Phase 1.5 item. |
| Pydantic + YAML | dataclasses + TOML (`tomllib`) | TOML parsing is in the stdlib from Python 3.11. Validation errors still name the bad field. |
| httpx (async) | urllib (sync) | One call at a time needs no async. Batch (Phase 2) is the point to add httpx. |
| `aicli config --set anthropic.key $KEY` | `api_key_env = "ANTHROPIC_API_KEY"` | A key written into a config file eventually gets pasted into an issue. The config stores the variable's name, not the secret. |
| Default model `claude-sonnet` | Default `local/llama3.2`, `fallback = []` | The PRD's first value is "privacy by default / local-first". Falling back from local to cloud would send the prompt off the machine, so the user has to opt in by listing a cloud model in `fallback`. |

Other choices:

- **Unknown prices report `n/a`, not `$0`.** A confident zero in a cost report is
  worse than an honest unknown. Prices carry a `PRICES_AS_OF` date. Override them in `[prices]`.
- **Failed attempts are stored in history** (`status = 'error'`), so every
  fallback can be audited later.
- **Anthropic `stop_reason: "refusal"` is an error.** It comes back as HTTP 200
  with no text, and printing an empty string would hide it.
