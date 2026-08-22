# Claude Instructions for claude-command-cli

## Role

Claude is the primary developer for this project. This document defines the scope, constraints, and best practices for maintaining and extending the architecture.

## Architecture to Maintain

```
┌─────────────────────────────────────────────────────┐
│                 Three-Layer Architecture            │
└─────────────────────────────────────────────────────┘

Layer 1: Termux CLI (Local)
├── Bash-based command runner
├── Sends encrypted commands to warnetech-server
├── Opens Claude chats with repo context
├── Manages local configuration (~/.claude-cli/config.json)
└── Handles git push/pull operations

Layer 2: warnetech-server (CANONICAL)
├── Receives encrypted CLI commands
├── Authenticates via API_KEY
├── Routes to handlers (warnetech_server/routes.py)
├── Calls control-plane, Supabase, external intel
├── Returns JSON responses
└── Opens/seals the warnetech_envelope (AES-256-GCM)

Layer 2b: Cloudflare Worker (LEGACY — test harness only)
├── worker/ + wrangler.toml, retained for the legacy Node CLI
├── NOT part of the canonical architecture
├── Do not add features here; add them to warnetech-server
└── See "Cloudflare status" below

Layer 3: GitHub Repository
├── Stores CLI scripts & executables
├── Stores server code + legacy Worker harness
├── Stores complete documentation
├── Stores Claude instructions (this file)
├── Tracks development on feature branches
└── Maintains version control & history
```

## Cloudflare status

The architecture is **Cloudflare-free and Termux-native**. The canonical
Layer 2 is `warnetech-server`, per
`docs/AI-FIREWALL-COMPLETE-REFERENCE.txt`, which lists the system as
relying only on warnetech-server, warnetech-control-plane,
warnetech-project-supabase, warnetech-backups and warnetech-cli.

`worker/` and `warnetech_cli_legacy/` are **legacy test harness**. They
still build and their tests still pass, so they are kept for regression
coverage of the wire format, but:

- No new features go into `worker/`. Add them to `warnetech_server/`.
- **Update (2026-08-07):** the 16 TODO stubs in `worker/` and
  `warnetech_cli_legacy/warnetech` previously described here as "will
  not be implemented" *were* implemented, at the user's explicit
  request. See the "Session update" entry at the bottom of TASKS.md for
  what shipped, what was intentionally scoped down (`evolve`/`update`
  don't match docs/09_AUTOMATION_PLAN.md's aspirational sandbox/rollback
  design — see the comments in `warnetech_cli_legacy/warnetech` for why),
  and what's still genuinely open (ChaCha20-Poly1305 fallback, Argon2id,
  data-tier enforcement, WORM logging, real Cloudflare deployment).
  Also fixed in the same pass: `worker/utils/validate.js`'s
  `decryptRequest()` unconditionally threw — this is the exact class of
  bug the paragraph below warns about ("that is what broke the
  CLI/Worker channel"), just never actually wired up in the first place.
- `docs/06_WORKER_SPEC.md` describes the legacy harness, not the
  canonical contract.

The canonical CLI is `warnetech_cli/` (Python), talking to
`warnetech-server` over the `warnetech_envelope` AES-256-GCM channel.

## Principles

### 1. Separation of Concerns

- **CLI layer**: Local operations, user I/O, config management
- **Server layer**: Remote logic, external API coordination, security
- **Repo layer**: Code storage, documentation, version control

Keep each layer independent. Don't move server logic to CLI or vice versa.

### 2. Security First

- All network communication: **AES-256-GCM encrypted**
- Fallback: **ChaCha20-Poly1305**
- Key derivation: **Argon2id**
- Never log plaintext secrets
- Validate all inputs at boundaries
- Use timing-safe comparisons for secrets

### 3. Modular Commands

Each command should:

- Have its own handler (warnetech_server/routes.py)
- Be independent from other commands
- Include error handling
- Support CLI piping/chaining
- Have clear help documentation

### 4. Atomic Commits

- One feature per commit
- Working code (tests pass)
- Clear commit message following format:
  ```
  <type>: <description>

  <optional details>
  ```
- Types: feat, fix, refactor, test, docs, chore

### 5. Documentation First

- Update docs before or alongside code
- Keep architecture diagram synchronized
- Document new endpoints in docs/06_WORKER_SPEC.md (legacy) or the
  warnetech-server route table
- Add commands to CLI_COMMANDS.md
- Explain non-obvious logic with comments

## Development Workflow

### Starting a Feature

```bash
# Start from development branch
git checkout claude/termux-cli-cloudflare-nemotron-pve6ca

# Create feature branch
git checkout -b feat/feature-name

# Make changes
# Test locally with: npm test

# Commit
git add .
git commit -m "feat: add new feature"

# Push
git push -u origin feat/feature-name
```

### Merging Back

```bash
# After testing/review
git checkout claude/termux-cli-cloudflare-nemotron-pve6ca
git merge feat/feature-name
git push origin claude/termux-cli-cloudflare-nemotron-pve6ca

# Delete feature branch
git branch -d feat/feature-name
```

## Safe Extension Patterns

### Adding a New CLI Command

1. **Create handler in warnetech_server/routes.py**

   ```python
   def handle_newcmd(req: Request, deps: ServerDependencies) -> Response:
       return Response(status=200, body={"result": ...})
   ```

2. **Register the route** in the router table in `routes.py`

3. **Add the CLI command in warnetech_cli/commands.py**, calling it
   through `ServerClient` so the request is sealed in the
   `warnetech_envelope`

4. **Document in docs/05_CLI_COMMANDS.md**

5. **Test**
   ```bash
   pytest tests/
   ```

### Adding a New API Integration

1. **Create a connector in warnetech_connectors/**

   ```python
   def fetch_newapi(source: str, config: ConnectorsConfig = DEFAULT_CONFIG) -> dict:
       ...
   ```

2. **Use it from the server or AI controller**

   ```python
   from warnetech_connectors.newapi import fetch_newapi
   result = fetch_newapi(source)
   ```

3. **Add error handling** — connectors fail soft, returning
   `{"error": ...}` rather than raising

4. **Test in isolation**
   ```bash
   pytest tests/connectors/
   ```

### Adding a New Utility Function

- Keep utilities focused (one responsibility)
- Place in appropriate utils/ directory
- Export as named function or default
- Add unit tests immediately
- Document with JSDoc comment

### Extending Security

- New encryption: extend `warnetech_envelope` — never add a second
  implementation; that is what broke the CLI/Worker channel
- New validation: add to `warnetech_server/security.py`
- New middleware check: add to the chain in `warnetech_server/middleware.py`
- Always maintain backward compatibility

## Things to Avoid

### ❌ Do NOT

- Hardcode API keys or secrets anywhere
- Log plaintext sensitive data
- Mix CLI and server logic
- Create circular dependencies
- Skip tests when committing
- Force push to main/master branch
- Change the three-layer architecture
- Add heavy dependencies without justification
- Remove existing functionality without discussing first
- Commit node_modules or build artifacts

### ✅ Do Instead

- Use environment variables for secrets
- Log only sanitized data
- Keep layers separated
- Use modular imports
- Run full test suite before commits
- Use force-with-lease if absolutely necessary
- Extend architecture within existing pattern
- Justify new dependencies in commit message
- Maintain backward compatibility
- Deprecate gracefully before removing

## Environment Setup

### Required

```bash
# Python — there is no requirements.txt; dependencies are declared in
# pyproject.toml. The dev extra pulls in pytest and ruff.
pip install -e ".[dev]"
pytest -q                  # Python tests
ruff check .               # Python lint

# JavaScript
npm install
npm run lint    # ESLint
npm run format  # Prettier
npm test        # Jest
```

### Local Development

```bash
# Terminal 1: Start warnetech-server
python -m warnetech_server.app

# Terminal 2: Test CLI commands
python -m warnetech_cli.main status
```

### Deployment

```bash
# Deploy warnetech-server
python -m warnetech_server.app

# Verify deployment
curl http://localhost:8080/health
```

## Code Review Checklist

Before committing, verify:

- [ ] Code follows 04_CODE_STANDARDS.md
- [ ] No secrets in code or commit message
- [ ] Tests added/updated (>80% coverage)
- [ ] Lint passes: `npm run lint`
- [ ] Format passes: `npm run format`
- [ ] Architecture diagram still accurate
- [ ] Documentation updated
- [ ] Commit message follows format
- [ ] Feature works end-to-end
- [ ] Error handling is robust

## Testing Strategy

### Unit Tests

- Test each module in isolation
- Mock external APIs
- Test error cases
- Aim for >80% coverage

```bash
pytest tests/ -k server
```

### Integration Tests

- Test full CLI → server → API flow
- Test encryption/decryption round-trip
- Test error propagation

```bash
npm run test:integration
```

### Manual Testing

```bash
# Test locally
npm run dev

# In another terminal
./warnetech_cli_legacy/warnetech ai "explain this code"
./warnetech_cli_legacy/warnetech gh-open "tewartech-node/claude-command-cli"
./warnetech_cli_legacy/warnetech status
```

## Documentation Maintenance

Keep these synchronized:

- **02_ARCHITECTURE_MAP.md** - Update if architecture changes
- **05_CLI_COMMANDS.md** - Add new commands here
- **06_WORKER_SPEC.md** - Legacy Worker harness only
- **04_CODE_STANDARDS.md** - Update standards if needed
- **03_TASKS_FOR_CLAUDE.md** - Check off completed tasks

## Version Control

### Branch Strategy

- **Development**: `claude/termux-cli-cloudflare-nemotron-pve6ca`
- **Features**: `feat/feature-name` (from development)
- **Fixes**: `fix/issue-name` (from development)
- **Main**: `main` (production-ready, auto-deployed)

### Commit Message Format

```
feat: add warnetech ai command
fix: handle rate limit responses
refactor: improve encryption utils
test: add integration tests
docs: update architecture diagram
chore: upgrade dependencies
```

## When to Ask for Help

Ask the user (don't just decide) when:

- Removing significant functionality
- Making major architecture changes
- Changing security/encryption approach
- Adding large external dependencies
- Significantly refactoring core modules
- Unsure about design decision
- Encountering conflicts that can't be resolved

## Common Tasks

### Adding a New Command

1. Create handler in warnetech_server/routes.py
2. Register the route in routes.py
3. Add CLI command in warnetech_cli/commands.py
4. Add tests
5. Document in 05_CLI_COMMANDS.md
6. Commit: `feat: add warnetech <cmd> command`

### Fixing a Bug

1. Create feature branch `fix/description`
2. Write failing test that reproduces bug
3. Fix the bug
4. Verify test passes
5. Commit: `fix: resolve issue description`

### Updating Documentation

1. Edit relevant markdown file
2. Update related files (architecture, standards)
3. Verify links still work
4. Commit: `docs: update documentation topic`

### Deploying Changes

1. Ensure all tests pass: `npm test`
2. Ensure lint passes: `npm run lint`
3. Merge to development branch
4. Push to remote
5. GitHub Actions automatically deploys to staging
6. After verification, merge to main for production

## Success Criteria

A feature is complete when:

- ✅ Code is implemented and tested
- ✅ Tests pass (>80% coverage)
- ✅ Lint & format pass
- ✅ Documentation updated
- ✅ End-to-end testing passed
- ✅ Committed with clear message
- ✅ Pushed to remote
- ✅ Architecture maintained
- ✅ No security issues introduced
- ✅ No secrets leaked

## Contact & Escalation

If you encounter issues:

1. Check the documentation first
2. Review similar implementations
3. Check git history for context
4. Run tests to identify failures
5. Ask user if blocked or uncertain

## Final Reminder

This architecture is proven and stable. Extend it carefully:

- Don't break the three-layer separation
- Maintain security standards
- Keep code modular and testable
- Document as you go
- Test thoroughly
- Commit atomically
- Keep the user informed

Good luck! 🚀
