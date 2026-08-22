# CLI Commands Reference

> **Legacy CLI.** This documents `warnetech_cli_legacy/warnetech` (the
> original Node.js CLI, deprecated but kept for its GitHub, AI-chat, and
> self-evolution commands). The canonical CLI is now the Python
> `warnetech_cli` package, which talks to warnetech-server's real HTTP
> API — see `warnetech_cli/main.py` for its command surface
> (`status`, `metrics`, `signatures`, `learn`, `recover`, `slice`,
> `compress`, `ghost-create`/`ghost-recall`, `retention-apply`/`retention-policy`,
> `ai-query`/`ai-recall`, `export`/`import`, `server-ping`, `db-check`,
> `db-sync`). The `warnetech <command>` examples below document the legacy
> binary's real invocation syntax (the entrypoint file itself is
> `warnetech_cli_legacy/warnetech`, not `warnet`).

## Core Commands

### warnetech ai

```bash
warnetech ai "<prompt>"
```

Sends a prompt to NVIDIA Nemotron 3 Ultra for AI assistance.

**Options:**

- `--stream`: Stream reasoning tokens in real-time
- `--timeout 30`: Set timeout in seconds (default: 30)
- `--model nemotron-3-ultra`: Specify model (default: nemotron-3-ultra)

**Example:**

```bash
warnetech ai "explain this code snippet"
warnetech ai "generate a bash script to backup files" --stream
```

**Flow:**

1. CLI reads prompt & options
2. CLI encrypts request (AES-256-GCM)
3. CLI sends to Worker via HTTPS
4. Worker calls NVIDIA API
5. Worker streams or buffers response
6. CLI decrypts & displays output

---

### warnetech fix

```bash
warnetech fix "<file_path>"
```

Uses AI to analyze and suggest fixes for a file.

**Example:**

```bash
warnetech fix "script.sh"
warnetech fix "src/index.js"
```

**Flow:**

1. CLI reads file from disk
2. CLI sends to Worker with file content
3. Worker calls AI with diagnostic prompt
4. Returns suggested fixes
5. CLI displays fixes with option to apply

---

### warnetech explain

```bash
warnetech explain "<file_path>"
```

Generates explanation for code in a file.

**Example:**

```bash
warnetech explain "src/utils/crypto.js"
warnetech explain "worker/index.js"
```

---

### warnetech update

```bash
warnetech update
```

Updates the CLI to latest version from GitHub.

**Options:**

- `--check`: Only check for updates, don't install
- `--version <version>`: Install specific version

**Flow:**

1. Checks GitHub releases for new version
2. Downloads new version
3. Verifies signature
4. Backs up current version to R2
5. Atomically deploys new version
6. Verifies functionality

---

### warnetech status

```bash
warnetech status
```

Displays current system status and configuration.

**Output:**

```
CLI Version: 1.0.0
API Status: ✓ Connected
Config: ~/.claude-cli/config.json
Latest Sync: 2026-08-05 10:15:00
Quotas:
  - API Calls: 45/100 (daily)
  - Storage: 2.3GB/10GB
  - Rate Limit: 60/100 (per minute)
```

---

### warnetech sync

```bash
warnetech sync
```

Synchronizes local state with remote (quotas, baselines, signatures).

**Syncs:**

- Quota information from warnetech
- Baseline signatures for anomaly detection
- Rate limit rules
- Configuration updates

---

### warnetech help

```bash
warnetech help [command]
```

Shows help for commands. Can query AI for complex errors.

**Examples:**

```bash
warnetech help
warnetech help ai
warnetech help --error "connection timeout"
```

---

## GitHub Commands

### warnetech gh-open

```bash
warnetech gh-open "<repo>"
```

Opens GitHub repository in browser or opens Claude with repo context.

**Examples:**

```bash
warnetech gh-open "tewartech-node/claude-command-cli"
warnetech gh-open "."  # current directory repo
```

---

### warnetech gh-push

```bash
warnetech gh-push "<commit_message>"
```

Commits and pushes changes to GitHub.

**Options:**

- `--branch <branch>`: Push to specific branch (default: current)
- `--no-verify`: Skip pre-commit hooks
- `--force`: Force push (careful!)

**Example:**

```bash
warnetech gh-push "feat: add warnetech ai command"
```

**Flow:**

1. CLI validates changes
2. CLI commits with message
3. CLI pushes to remote
4. CLI displays result

---

### warnetech gh-pull

```bash
warnetech gh-pull
```

Pulls latest changes from remote repository.

**Options:**

- `--rebase`: Use rebase instead of merge
- `--branch <branch>`: Pull specific branch

---

## System Commands

### warnetech evolve

```bash
warnetech evolve
```

Self-updates the CLI with new features (ASAEAI synthesis pattern).

**Process:**

1. Downloads latest code from GitHub
2. Runs sandbox synthesis tests
3. Verifies changes with automated tests
4. Performs atomic deployment
5. Verifies functionality
6. Can rollback if needed

**Stages:**

- Synthesis: Generate/apply code changes
- Verification: Test in isolated environment
- Deployment: Atomic update
- Rollback: Revert if needed

---

### warnetech request-score

```bash
warnetech request-score "<description>"
```

Requests AI reinforcement scoring for a task or output.

**Example:**

```bash
warnetech request-score "quality of generated code"
```

---

## Configuration Command

### warnetech init

```bash
warnetech init
```

Initializes ~/.claude-cli/config.json with defaults.

**Creates:**

```json
{
  "api_key": "your-key-here",
  "worker_url": "https://your-worker.workers.dev",
  "nemotron_api_key": "your-nemotron-key",
  "github_token": "your-github-token",
  "tier": 2,
  "cache_dir": "~/.claude-cli/cache"
}
```

---

## Advanced Commands

### warnetech quota

```bash
warnetech quota [check|rollup]
```

**check:** Show current quota usage
**rollup:** Trigger quota rollup operation

---

### warnetech detect-anomalies

```bash
warnetech detect-anomalies
```

Triggers anomaly detection against stored baselines.

---

### warnetech sync-signatures

```bash
warnetech sync-signatures
```

Syncs baseline signatures from warnetech control plane.

---

## Output Format

### Success

```bash
$ warnetech ai "hello"
✓ Prompt sent
> Processing...
[AI Response]
```

### Error with AI Explanation

```bash
$ warnetech ai "bad prompt"
✗ Error: Invalid prompt format
> Would you like AI explanation? Run: warnetech help --error "Invalid prompt format"
```

### Status Display

```bash
$ warnetech status
✓ System Status
  Version: 1.0.0
  Config: ~./claude-cli/config.json
  Worker: Connected
  Cache: 256MB used
```

---

## Exit Codes

- 0: Success
- 1: General error
- 2: Invalid command
- 3: Authentication error
- 4: Connection error
- 5: Timeout

---

## Tips

### Piping

```bash
cat file.js | warnetech explain -  # read from stdin
warnetech ai "generate script" | tee output.sh
```

### Chaining

```bash
warnetech fix "buggy.js" && warnetech ai "test this" && warnetech gh-push "fix: resolved"
```

### Background Jobs

```bash
warnetech update &  # update in background
warnetech evolve &  # self-update in background
```
