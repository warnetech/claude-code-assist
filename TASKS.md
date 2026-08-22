# Tasks for Claude

This is Claude's working to-do list for the claude-command-cli project. Tasks are organized by priority and dependency.

## Core Tasks

These are the primary development goals.

### 1. Improve the Termux CLI Script

**Status**: ✅ Phase 1 Complete (Core Features)

**What**: Enhance warnetech_cli_legacy/warnetech with full functionality

**Subtasks**:

- [x] Implement command parser (Commander.js)
- [x] Add config file loading (~/.claude-cli/config.json)
- [x] Implement request encryption (AES-256-GCM) — was already wired
      client-side; the Worker never actually decrypted it until
      2026-08-07 (see CLAUDE.md's Cloudflare status section)
- [ ] Implement response decryption — CLI can decrypt an encrypted
      response, but the Worker never sends one (`respondEncrypted()` in
      worker/utils/respond.js is defined but unused); still open
- [x] Add error handling & helpful messages
- [x] Add progress indicators & formatting
- [x] Test with actual Worker — exercised end-to-end against a local
      Worker instance over real HTTP (2026-08-07); not yet against an
      actual Cloudflare deployment
- [ ] Add bash completions
- [ ] Package as standalone binary

**Related Docs**:

- [05_CLI_COMMANDS.md](docs/05_CLI_COMMANDS.md) - Command reference
- [04_CODE_STANDARDS.md](docs/04_CODE_STANDARDS.md) - Coding guidelines

---

### 2. Improve the Cloudflare Worker Code

**Status**: ✅ Phase 1 Complete (Core Handlers)

**What**: Build production-ready Worker with all handlers

**Subtasks**:

- [x] Implement basic request validation (validateRequest)
- [x] Implement AES-256-GCM encryption/decryption — decryptRequest() now
      actually calls crypto.js's decryptData() instead of hard-throwing
      (2026-08-07)
- [ ] Implement ChaCha20-Poly1305 fallback
- [ ] Implement Argon2id key derivation (still PBKDF2)
- [x] Implement HMAC-SHA256 signature verification — verified in
      decryptRequest() against the request's `signature` field
- [x] Add anti-tamper checks — signature + X-API-Key-Hash + timestamp
      window enforced in the /cli request path
- [ ] Add data tier enforcement — tiers are computed (getDataTier) but
      nothing gates on them yet
- [x] Implement rate limiting (Cloudflare KV) — worker/utils/security.js,
      fails open (allows the request) without a KV binding
- [x] Add comprehensive error handling
- [ ] Add request/response logging (WORM storage)
- [x] Test all endpoints (unit tests)
- [ ] Deploy to Cloudflare — wrangler.toml now declares the
      `nodejs_compat` flag and documents the KV/API_KEY/
      WARNETECH_SERVER_URL bindings this code needs, but nothing has
      actually been deployed

**Related Docs**:

- [06_WORKER_SPEC.md](docs/06_WORKER_SPEC.md) - Worker specification
- [04_CODE_STANDARDS.md](docs/04_CODE_STANDARDS.md) - Code standards

---

### 3. Add New CLI Commands

**Status**: ✅ Phase 1 Complete (Phase 2 Ready)

**Commands Implemented** (Phase 1):

#### Phase 1 - Core Commands ✅

- [x] `warnetech ping` - Test connectivity (CRITICAL)
  - [x] CLI implementation
  - [x] Worker endpoint
  - [x] Request/response formatting
  - [x] Tests

- [x] `warnetech gh-open "<repo>"` - GitHub Claude link (CRITICAL)
  - [x] Validate repo URL format
  - [x] Generate Claude link
  - [x] Display URLs
  - [x] Tests

- [x] `warnetech ai "<prompt>"` - NVIDIA Nemotron integration (HIGH)
  - [x] Basic prompt sending
  - [x] Response parsing
  - [x] Token counting
  - [x] Error handling
  - [x] Tests

- [x] `warnetech gh-push "<message>"` - Git automation (HIGH)
  - [x] Git add changes
  - [x] Git commit with message
  - [x] Git push to remote
  - [x] Merge conflict handling
  - [x] Tests

- [x] `warnetech gh-pull` - Pull changes (HIGH)
  - [x] Git fetch origin
  - [x] Git pull with merge/rebase
  - [x] Conflict handling
  - [x] Tests

#### Phase 2 - Intermediate Commands (In Progress)

- [x] `warnetech fix "<file>"` - Code fixing (2026-08-07)
  - [x] Read file content
  - [x] Send to AI with diagnostic prompt
  - [x] Display suggestions
  - [x] Option to apply fixes — `--apply`: asks the AI for a unified
        diff, backs up the file to `<file>.bak`, applies via `git apply`

- [x] `warnetech explain "<file>"` - Code explanation (2026-08-07)
  - [x] Read file content
  - [x] Generate explanation prompt
  - [x] Display formatted explanation

#### Phase 3 - System Commands (Planned)

- [x] `warnetech status` - System status (2026-08-07)
  - [x] Check Worker connectivity
  - [x] Show quota usage
  - [x] Display version info
  - [x] Show config status

- [x] `warnetech sync` - Sync remote state (2026-08-07)
  - [x] Fetch baselines / [x] Update signatures — both relayed through
        `sys sync`, which is honest ("WARNETECH_SERVER_URL not
        configured") when there's no warnetech-server to talk to
        instead of fabricating a result
  - [ ] Sync quotas — quota tracking lives in `warnetech quota`/`status`,
        not merged into `sync`
  - [ ] Check for updates — that's `warnetech update`, kept separate

- [~] `warnetech update` - Update CLI (2026-08-07, scoped down)
  - [x] Check latest version — via `git fetch` + `rev-list --count`
        against the current branch's origin, not a GitHub Releases API
  - [ ] Download new version / [ ] Verify signature / [ ] Atomic
        replacement — no signed-release pipeline exists in this repo;
        `update` pulls the current git branch instead (see the comment
        above the command in warnetech_cli_legacy/warnetech)
  - [x] Verify functionality — reports the new commit/version after pulling

- [~] `warnetech evolve` - Self-update with AI synthesis (2026-08-07, scoped down)
  - [x] Synthesis: Generate changes — asks the AI for suggestions based
        on the repo's own TODO comments
  - [ ] Verification: Test in sandbox / [ ] Deployment: Atomic update /
        [ ] Rollback: Restore if needed — intentionally NOT built. An
        unattended pipeline that lets a CLI rewrite and redeploy its own
        code is a real safety hazard, and docs/09_AUTOMATION_PLAN.md's
        design (D1 patch queue, staging Worker deploys, AST mutation
        engine) doesn't exist anywhere in this codebase to build on top
        of. `evolve` prints suggestions and stops, deferring review/apply
        to a human (e.g. via `warnetech fix <file> --apply`).

- [x] `warnetech help [cmd]` - Help system
  - [x] Show general help (pre-existing)
  - [x] Show command-specific help (pre-existing)
  - [x] AI-powered error explanation (`--error`) (2026-08-07)

#### Secondary Commands

- [x] `warnetech init` - Initialize configuration (2026-08-07; `--force`
      to overwrite, config file written 0600 since it holds secrets)
- [ ] `warnetech quota` - Quota management — `sys quota check` exists
      server-side (used by `status`) but isn't its own top-level CLI command
- [ ] `warnetech detect-anomalies` - Security monitoring — same story;
      `sys detect-anomalies` exists server-side, no dedicated CLI command
- [ ] `warnetech sync-signatures` - Sync baselines
- [ ] `warnetech request-score` - AI reinforcement scoring

**Related Docs**:

- [05_CLI_COMMANDS.md](docs/05_CLI_COMMANDS.md) - Full command reference

---

### 4. Add New Worker Endpoints

**Status**: 🔄 In Progress (Foundation Ready)

**Endpoints to Implement**:

#### Command Endpoints

- [ ] `POST /api/command` (Main)
  - [ ] Route to ai.js handler
  - [ ] Route to gh.js handler
  - [ ] Route to sys.js handler

#### Health & Status

- [ ] `GET /health` - Health check
  - [ ] Return status info
  - [ ] Check dependencies

- [ ] `GET /health/detailed` - Detailed health
  - [ ] D1 connection status
  - [ ] R2 bucket status
  - [ ] KV namespace status
  - [ ] Supabase connection status
  - [ ] NVIDIA API quota

#### Authentication

- [ ] `POST /api/authenticate` - Key negotiation
  - [ ] Validate public key
  - [ ] Return session token
  - [ ] Implement ML-KEM handshake

#### Hot Reload (Evolution)

- [ ] `POST /api/hotload` - Deploy patches
  - [ ] Validate patch code
  - [ ] Apply changes in-memory
  - [ ] Run smoke tests
  - [ ] Log deployment

#### Monitoring

- [ ] `GET /api/metrics` - Performance metrics
  - [ ] Request counts
  - [ ] Latency stats
  - [ ] Error rates

- [ ] `GET /api/logs` - Audit logs
  - [ ] Require authentication
  - [ ] RLS enforcement
  - [ ] WORM validation

**Related Docs**:

- [06_WORKER_SPEC.md](docs/06_WORKER_SPEC.md) - Worker specification

---

### 5. Add GitHub Automation Features

**Status**: 🔄 In Progress (Foundation Ready)

**Features to Implement**:

#### GitHub Commands

- [ ] `gh-open` - Open repo in Claude
  - [ ] Verify repo URL
  - [ ] Generate Claude link
  - [ ] Open if browser available

- [ ] `gh-push` - Commit & push
  - [ ] Git add files
  - [ ] Commit with message
  - [ ] Push to remote
  - [ ] Handle authentication

- [ ] `gh-pull` - Pull changes
  - [ ] Fetch latest
  - [ ] Merge or rebase
  - [ ] Resolve conflicts
  - [ ] Push if needed

#### GitHub Actions Workflow

- [ ] Create linting workflow
  - [ ] ESLint
  - [ ] Prettier
  - [ ] Fail on issues

- [ ] Create testing workflow
  - [ ] Unit tests
  - [ ] Integration tests
  - [ ] Coverage reporting

- [ ] Create deployment workflow
  - [ ] Worker deployment (staging)
  - [ ] CLI release build
  - [ ] Publish artifacts
  - [ ] Deploy to production (main branch)

#### Claude Integration

- [ ] Worker endpoint for Claude redirect
  - [ ] GET /api/claude-link
  - [ ] Returns: `https://claude.ai/new?repo=...`

- [ ] Termux command to open Claude
  - [ ] `warnetech gh-open <repo>` opens Claude
  - [ ] Pre-fills repo context

**Related Docs**:

- [05_CLI_COMMANDS.md](docs/05_CLI_COMMANDS.md) - GitHub commands

---

### 6. Add AI-Powered Code Correction Tools

**Status**: 🔄 In Progress (Foundation Ready)

**Features to Implement**:

#### Code Analysis

- [ ] `warnetech fix "<file>"` - Fix code issues
  - [ ] Read file
  - [ ] Send to Nemotron with diagnostic prompt
  - [ ] Parse response for fixes
  - [ ] Display issues & suggestions
  - [ ] Option to apply (with backup)

- [ ] `warnetech explain "<file>"` - Explain code
  - [ ] Read file
  - [ ] Generate explanation prompt
  - [ ] Call Nemotron
  - [ ] Display formatted explanation

- [ ] `warnetech help --error "<message>"` - Error explanation
  - [ ] Send error to Nemotron
  - [ ] Get explanation & solution
  - [ ] Display troubleshooting steps

#### NVIDIA Nemotron Integration

- [ ] Implement nemotron.js client
  - [ ] Chat endpoint
  - [ ] Streaming support
  - [ ] Reasoning tokens
  - [ ] Error handling
  - [ ] Token counting

- [ ] Prompt optimization
  - [ ] AST mutation for clarity
  - [ ] Add context automatically
  - [ ] Format examples
  - [ ] Enforce constraints

- [ ] Response handling
  - [ ] Parse AI responses
  - [ ] Format for CLI display
  - [ ] Highlight code blocks
  - [ ] Handle truncation

#### Specialized Prompts

- [ ] Code fixing prompt
  - [ ] Identify bugs
  - [ ] Explain issues
  - [ ] Suggest fixes
  - [ ] Rate severity

- [ ] Code explanation prompt
  - [ ] High-level overview
  - [ ] Function breakdown
  - [ ] Data flow
  - [ ] Dependencies

- [ ] Error diagnosis prompt
  - [ ] Explain root cause
  - [ ] Troubleshooting steps
  - [ ] Prevention tips
  - [ ] Related issues

**Related Docs**:

- [07_AI_INTEGRATION.md](docs/07_AI_INTEGRATION.md) - NVIDIA integration
- [05_CLI_COMMANDS.md](docs/05_CLI_COMMANDS.md) - Command reference

---

## Secondary Tasks

These tasks improve code quality and maintainability.

### Refactor Code for Clarity

**Status**: 🔄 In Progress

**Goals**:

- [ ] Extract common patterns to utils
- [ ] Simplify error handling
- [ ] Remove duplication
- [ ] Improve variable naming
- [ ] Add JSDoc comments (for non-obvious logic only)

**Related Docs**:

- [04_CODE_STANDARDS.md](docs/04_CODE_STANDARDS.md) - Code standards

---

### Add Documentation

**Status**: ✅ Mostly Complete

**What's Done**:

- ✅ Project goals & vision
- ✅ Architecture documentation
- ✅ Code standards & guidelines
- ✅ CLI commands reference
- ✅ Worker specification
- ✅ NVIDIA integration guide
- ✅ Git workflow guide
- ✅ Self-update automation plan
- ✅ Claude instructions

**What's Remaining**:

- [ ] API endpoint documentation
- [ ] Configuration guide
- [ ] Troubleshooting guide
- [ ] Security guide
- [ ] Deployment guide
- [ ] Contributing guide

---

### Add Examples

**Status**: 🔄 In Progress

**Examples to Create**:

- [ ] Example CLI usage
- [ ] Example API requests
- [ ] Example responses
- [ ] Example error handling
- [ ] Example custom commands
- [ ] Example Worker deployment

---

### Add Error Handling

**Status**: 🔄 In Progress

**Where to Add**:

- [ ] CLI command validation
- [ ] Worker request validation
- [ ] API error responses
- [ ] Network timeout handling
- [ ] Encryption/decryption errors
- [ ] File I/O errors
- [ ] Git operation errors
- [ ] NVIDIA API errors

**Pattern**:

```javascript
try {
  // operation
} catch (error) {
  // User-friendly error message
  // Suggest next steps
  // Log for debugging
}
```

---

### Add Modular Command Files

**Status**: ✅ Complete

**Created**:

- ✅ worker/commands/ai.js
- ✅ worker/commands/gh.js
- ✅ worker/commands/sys.js
- ✅ worker/utils/validate.js
- ✅ worker/utils/respond.js
- ✅ worker/utils/nemotron.js

**Pattern for New Commands**:

```javascript
// worker/commands/newcmd.js
async function handleNewcmd(args, env) {
  // Implementation
  return result;
}

export default handleNewcmd;
```

---

## Rules to Follow

### Security

- ❌ **Never** store secrets in repo
- ✅ Use environment variables
- ✅ Use Cloudflare secrets
- ✅ Encrypt sensitive data
- ✅ Never log plaintext secrets
- ✅ Sanitize user input
- ✅ Use timing-safe comparisons

### Compatibility

- ✅ **Keep everything free-tier compatible**
  - Cloudflare free tier limits
  - NVIDIA free API tier
  - GitHub free tier

- ✅ **Maintain Termux compatibility**
  - Node.js available
  - Bash available
  - No special permissions needed

- ✅ **Maintain Cloudflare Workers compatibility**
  - No file system access
  - Max 50MB code size
  - 30 second timeout
  - Limited CPU

- ✅ **Maintain NVIDIA Nemotron compatibility**
  - Use correct endpoint
  - Follow API specifications
  - Track token usage
  - Handle rate limits

### Code Quality

- ✅ Follow [04_CODE_STANDARDS.md](docs/04_CODE_STANDARDS.md)
- ✅ Write tests for new features
- ✅ Keep >80% test coverage
- ✅ Run lint & format before commit
- ✅ One feature per commit
- ✅ Clear commit messages
- ✅ Update documentation

---

## Progress Tracking

### Completed Tasks

- ✅ Project architecture designed
- ✅ Repository scaffolding created
- ✅ Documentation written (9 files)
- ✅ CLAUDE.md instructions created
- ✅ ARCHITECTURE.md designed
- ✅ Core command handlers scaffolded
- ✅ Utility functions scaffolded
- ✅ package.json configured
- ✅ Branch created & pushed
- ✅ Phase 1 CLI commands implemented (5 commands)
  - ✅ warnetech ping (connectivity test)
  - ✅ warnetech gh-open (GitHub Claude links)
  - ✅ warnetech ai (NVIDIA Nemotron AI)
  - ✅ warnetech gh-push (git commit & push)
  - ✅ warnetech gh-pull (git pull)
- ✅ Test suite created (14 tests, all passing)
- ✅ Jest configuration for ES modules
- ✅ Wrangler configuration for Cloudflare Worker
- ✅ Error handling & user-friendly messages
- ✅ Config file loading from ~/.claude-cli/config.json

### Current Phase

✅ **Phase 1: Foundation & CLI Implementation - COMPLETE**

**Completed This Session**:

1. ✅ Implemented CLI command parser (Commander.js)
2. ✅ Added config file loading (~/.claude-cli/config.json)
3. ✅ Created first 5 working CLI commands (ping, gh-open, ai, gh-push, gh-pull)
4. ✅ Implemented Worker endpoints (/cli)
5. ✅ Added comprehensive error handling & helpful messages
6. ✅ Created test suite with 14 passing tests
7. ✅ Implemented git operations (push/pull)

**Next Phase (Phase 2)**:

- Implement `warnetech fix` command (code analysis)
- Implement `warnetech explain` command (code explanation)
- Add streaming support for AI responses (optional)
- Implement specialized prompts (diagnostic, explanation, error diagnosis)

### Timeline

**Week 1-2**: Foundation

- CLI scaffolding → production ready
- Worker foundations → core handlers
- Basic security → full encryption

**Week 3-4**: Core Features

- All CLI commands implemented
- All Worker handlers implemented
- GitHub integration working
- NVIDIA integration complete

**Week 5-6**: Infrastructure

- D1, R2, Supabase connected
- Rate limiting working
- Quota tracking functional
- Anomaly detection enabled

**Week 7-8**: Advanced Features

- Hot reload system
- AST mutation engine
- Self-update (warnetech evolve)
- Rollback capability

**Week 9-10**: Testing & Deployment

- Unit tests complete
- Integration tests complete
- End-to-end testing
- Production deployment

---

## How to Use This File

1. **Check Current Tasks**: Look at "Core Tasks" section
2. **Start Working**: Pick next unchecked task
3. **Update Progress**: Check off as you complete
4. **Related Docs**: Follow links to documentation
5. **Follow Rules**: Keep security & compatibility rules in mind

## Questions & Blockers

If you encounter:

- **Architecture questions** → Read ARCHITECTURE.md
- **Code questions** → Read CODE_STANDARDS.md
- **Security questions** → Read CLAUDE.md security section
- **Getting blocked** → Ask user for clarification

---

## Session Update (2026-08-07): Legacy Worker/CLI TODOs

At the user's explicit request (overriding CLAUDE.md's prior "will not
be implemented" note — see its Cloudflare status section), implemented
all 16 `// TODO:` stubs across `worker/` and
`warnetech_cli_legacy/warnetech`, plus two bugs found along the way:

- **`worker/utils/validate.js`'s `decryptRequest()` unconditionally
  threw** "not yet implemented" — every encrypted `/cli` request (which
  is all of them; the CLI always encrypts) was failing before this fix.
  Wired it to the already-correct `worker/utils/crypto.js` AES-256-GCM
  implementation, added HMAC signature verification and an
  X-API-Key-Hash fast-fail check. `worker/utils/crypto.js` was also
  missing a `hashApiKey` export needed for that check.
- **`gh.js`'s `ghOpen()` only returned `url`**, but the CLI destructures
  `{ url, claude_url }` — `claude_url` was always `undefined`. Fixed to
  return both, plus a new `repo_url` for the plain GitHub link.
- `worker/utils/security.js`: rate limiting and replay-ID dedup, both
  KV-backed, both fail-open (allow the request) without a KV binding.
  Wired into `worker/index.js`'s request flow.
- `worker/utils/nemotron.js`: streaming responses now request
  `stream_options.include_usage` and parse real token counts from the
  final SSE chunk instead of hardcoding zeros.
- `worker/commands/sys.js`: `quota`/`sync`/`detect-anomalies`/`rollup`
  now do real (KV- or WARNETECH_SERVER_URL-backed) work where possible,
  and say so honestly (`live: false`, `"not configured"`, etc.) rather
  than fabricating numbers when the backing infrastructure isn't there.
- `wrangler.toml`: added the `nodejs_compat` compatibility flag (required
  for `worker/utils/crypto.js`'s `node:crypto` import to resolve on the
  real Workers runtime — Jest didn't need it, a real deployment would),
  plus documented the `API_KEY`/KV/`WARNETECH_SERVER_URL` bindings this
  code now expects.
- `warnetech_cli_legacy/warnetech`: implemented `fix` (with `--apply`,
  via AI-generated unified diff + `git apply` + a `.bak` backup),
  `explain`, `status`, `sync`, `update` (git-based — see the "scoped
  down" notes above), `evolve` (synthesis-only, same reasoning), `help
  --error`, and `init` (0600-permissioned config file). Also fixed a
  pre-existing bug where `evolve --dry-run` read
  `options["dry-run"]`, which Commander never sets (it camelCases to
  `options.dryRun`) — the flag silently did nothing before this.
- Added Jest coverage for all of the above:
  `__tests__/worker/index.test.js` (full encrypted round trip),
  `__tests__/security/rate-limit.test.js`, `__tests__/commands/sys.test.js`,
  `__tests__/utils/nemotron.test.js`.

**Verification caveat**: this sandbox has no npm/pip registry access, so
the real `jest`/`pytest` suites could not be run directly. Everything
above was instead verified by executing the actual code: a temporary
Commander-compatible shim (not committed) let the real
`warnetech_cli_legacy/warnetech` binary run end-to-end against a local
HTTP server built from the real `worker/index.js`, covering every new
command plus `git`-based `update` against a real bare repo and
`fix --apply` against a real `git apply`. A second temporary harness
replayed all `__tests__/**/*.test.js` files (old and new) against the
real assertions those files already contain — 92/92 passed. Run the
real `npm test` once registry access is available to confirm under
actual Jest.

---

**Last Updated**: 2026-08-07
**Status**: 🚀 Active Development (v0.1.0)
