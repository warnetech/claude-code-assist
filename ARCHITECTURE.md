# System Architecture

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER MACHINE                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              LAYER 1: TERMUX CLI (Local)                  │  │
│  │                                                            │  │
│  │  $ warnetech ai "explain this code"                          │  │
│  │  $ warnetech gh-push "feat: new feature"                     │  │
│  │  $ warnetech status                                          │  │
│  │                                                            │  │
│  │  ├─ warnetech_cli_legacy/warnetech (Node.js/Bash)                     │  │
│  │  ├─ Config: ~/.claude-cli/config.json                    │  │
│  │  ├─ Sends encrypted requests (AES-256-GCM)              │  │
│  │  ├─ Receives JSON responses                              │  │
│  │  └─ Local git operations (push/pull)                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                         ↓ HTTPS                                  │
│                  Encrypted Request                               │
│                    (AES-256-GCM)                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      CLOUDFLARE EDGE                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │         LAYER 2: CLOUDFLARE WORKER (Remote)              │  │
│  │                                                            │  │
│  │  POST /api/command                                        │  │
│  │  ├─ Authenticate (API_KEY validation)                    │  │
│  │  ├─ Decrypt request (AES-256-GCM)                        │  │
│  │  ├─ Route to handler:                                    │  │
│  │  │  ├─ ai.js → NVIDIA Nemotron                           │  │
│  │  │  ├─ gh.js → GitHub API                                │  │
│  │  │  └─ sys.js → System operations                        │  │
│  │  ├─ Call external APIs                                   │  │
│  │  ├─ Format response (JSON)                               │  │
│  │  └─ Encrypt response (AES-256-GCM)                       │  │
│  │                                                            │  │
│  │  Infrastructure:                                          │  │
│  │  ├─ Cloudflare D1 (cache)                                │  │
│  │  ├─ Cloudflare R2 (backups)                              │  │
│  │  ├─ Cloudflare KV (rate limits)                          │  │
│  │  └─ Supabase Postgres (audit logs)                       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                         ↓ HTTPS                                  │
│                  Encrypted Response                              │
│                    (AES-256-GCM)                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     EXTERNAL SERVICES                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │         LAYER 3: GITHUB & EXTERNAL APIs                  │  │
│  │                                                            │  │
│  │  ├─ GitHub (tewartech-node/claude-command-cli)          │  │
│  │  │  ├─ Stores CLI scripts                                │  │
│  │  │  ├─ Stores Worker code                                │  │
│  │  │  ├─ Stores documentation                              │  │
│  │  │  └─ Tracks development & versions                     │  │
│  │  │                                                         │  │
│  │  ├─ NVIDIA Nemotron API                                  │  │
│  │  │  └─ AI-powered responses                              │  │
│  │  │                                                         │  │
│  │  ├─ Warnetech Control Plane                             │  │
│  │  │  ├─ Quota monitoring                                  │  │
│  │  │  ├─ Anomaly detection                                 │  │
│  │  │  └─ Baseline signatures                               │  │
│  │  │                                                         │  │
│  │  └─ GitHub API (automation)                              │  │
│  │     └─ Push/pull operations                              │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Request Flow (CLI → Worker)

```
1. User types: warnetech ai "explain code"
2. CLI reads ~/.claude-cli/config.json
3. CLI encrypts request (AES-256-GCM)
4. CLI sends HTTPS POST to Worker
   {
     command: 'ai',
     args: ['explain code'],
     encrypted: true,
     signature: 'hmac_signature'
   }
5. Worker receives request
6. Worker validates API_KEY (timing-safe)
7. Worker decrypts payload (AES-256-GCM)
8. Worker verifies signature (HMAC-SHA256)
9. Worker routes to ai.js handler
10. Handler calls NVIDIA Nemotron API
11. Handler processes response
12. Worker encrypts response (AES-256-GCM)
13. Worker returns JSON response
14. CLI receives encrypted response
15. CLI decrypts response (AES-256-GCM)
16. CLI displays formatted output
```

### Response Flow

```
1. AI Response arrives at Worker
2. Worker formats: { ok: true, data: {...} }
3. Worker encrypts response
4. Worker signs response (HMAC-SHA256)
5. HTTPS response sent to CLI
6. CLI decrypts response
7. CLI validates signature
8. CLI displays output to user
```

## Component Breakdown

### Layer 1: CLI (warnetech_cli_legacy/)

```
warnetech (main entrypoint)
├─ Commands:
│  ├─ ai <prompt>         → Send to AI
│  ├─ fix <file>          → Fix code
│  ├─ explain <file>      → Explain code
│  ├─ gh-open <repo>      → Open in Claude
│  ├─ gh-push <message>   → Commit & push
│  ├─ gh-pull             → Pull changes
│  ├─ status              → System status
│  ├─ sync                → Sync remote
│  ├─ update              → Update CLI
│  ├─ evolve              → Self-update
│  └─ help [cmd]          → Get help
│
├─ Config:
│  └─ ~/.claude-cli/config.json
│     ├─ api_key
│     ├─ worker_url
│     ├─ nemotron_api_key
│     ├─ github_token
│     └─ tier
│
└─ Utils:
   ├─ Encryption/Decryption
   ├─ API communication
   ├─ Config loading
   ├─ Git operations
   └─ Output formatting
```

### Layer 2: Worker (worker/)

```
index.js (HTTP handler)
├─ POST /api/command
│  ├─ validateRequest()
│  ├─ Route to handler
│  └─ formatResponse()
│
├─ GET /health
│  └─ Status check
│
└─ POST /api/authenticate
   └─ Key negotiation

commands/ (Handlers)
├─ ai.js
│  ├─ Parse prompt
│  ├─ Call NVIDIA API
│  ├─ Stream/buffer response
│  └─ Return result
│
├─ gh.js
│  ├─ gh-open: Get repo info
│  ├─ gh-push: Commit & push
│  └─ gh-pull: Pull changes
│
└─ sys.js
   ├─ status: System health
   ├─ quota: Usage info
   ├─ sync: Update baselines
   ├─ detect-anomalies: Security
   └─ rollup: Aggregate data

utils/ (Shared)
├─ validate.js
│  ├─ API key validation
│  ├─ Request signature verification
│  ├─ Anti-tamper checks
│  ├─ Encryption/Decryption
│  └─ Data tier enforcement
│
├─ respond.js
│  ├─ Success response format
│  └─ Error response format
│
└─ nemotron.js
   ├─ NVIDIA API client
   ├─ Prompt optimization
   ├─ Streaming support
   └─ Token tracking
```

### Layer 3: GitHub & External APIs

```
GitHub Repository
├─ /docs (9 specification files)
├─ /worker (Cloudflare Worker code)
├─ /warnetech_cli_legacy (CLI scripts)
├─ /scripts (Automation scripts)
├─ package.json
├─ README.md
├─ CLAUDE.md (Claude instructions)
└─ ARCHITECTURE.md (this file)

External Services
├─ NVIDIA Nemotron API
│  └─ https://integrate.api.nvidia.com/v1/chat/completions
│
├─ GitHub API
│  ├─ Repository operations
│  ├─ Push/pull operations
│  └─ Release management
│
├─ Warnetech Control Plane
│  ├─ Quota monitoring
│  ├─ Anomaly detection
│  └─ Signature management
│
└─ Cloudflare Services
   ├─ D1 Database
   ├─ R2 Object Storage
   ├─ KV Key-Value Store
   └─ Workers Platform
```

## Security Architecture

### Encryption Layers

```
                   AES-256-GCM (Primary)
                   ↓ Fallback ↓
                ChaCha20-Poly1305
                   ↓ Key ↓
                  Argon2id (KDF)

Request Path:
User Input
  ↓ (plaintext)
CLI
  ↓ (encrypt AES-256-GCM)
Network (HTTPS)
  ↓ (encrypted)
Worker
  ↓ (decrypt, validate signature)
Handler
  ↓ (process)
Response
  ↓ (encrypt AES-256-GCM)
Network (HTTPS)
  ↓ (encrypted)
CLI
  ↓ (decrypt, validate signature)
Output (formatted)
```

### Authentication Flow

```
1. CLI has API_KEY (stored in config)
2. CLI includes X-API-Key header (hashed)
3. Worker validates API_KEY (timing-safe comparison)
4. Worker checks X-Request-ID (prevent replay)
5. Worker validates X-Timestamp (within 5 min)
6. Worker verifies HMAC signature
7. Worker allows/denies request
```

### Data Tiers

```
TIER_1: Highly Sensitive
├─ Encrypted at rest
├─ Encrypted in transit
├─ Access logging
└─ Example: API keys, passwords

TIER_2: Sensitive
├─ Encrypted in transit only
├─ Audit logging
└─ Example: User code, prompts

TIER_3: Public
├─ No encryption required
├─ Public logging
└─ Example: Help text, status info
```

## Deployment Architecture

### Development

```
Local Machine
├─ npm run dev (Worker dev server)
├─ ./warnetech_cli_legacy/warnetech (CLI testing)
└─ npm test (Local testing)
```

### Staging

```
Cloudflare Edge (Staging)
├─ Deployed Worker
├─ D1 test database
├─ R2 test bucket
└─ KV test namespace
```

### Production

```
Cloudflare Edge (Production)
├─ Deployed Worker
├─ D1 production database
├─ R2 production bucket
├─ KV production namespace
└─ Supabase production DB
```

## Extension Points

### Adding Features

The architecture supports:

- ✅ New CLI commands (add to warnetech_cli_legacy/warnetech)
- ✅ New Worker handlers (add to worker/commands/)
- ✅ New API integrations (add to worker/utils/)
- ✅ New security checks (enhance worker/utils/validate.js)
- ✅ New infrastructure (add Cloudflare services)

### Safe Modifications

- Don't change the three-layer separation
- Don't hardcode secrets
- Don't break existing commands
- Don't skip tests
- Don't remove documentation
- Don't modify core security functions without review

## Monitoring & Observability

### Metrics

- Request latency (p50, p95, p99)
- Error rates (4xx, 5xx)
- Token usage (NVIDIA API)
- Rate limit hits (Cloudflare KV)
- Database queries (Supabase)

### Logging

- All requests logged (no plaintext secrets)
- Errors with stack traces
- Audit trail for security events
- WORM storage in R2
- RLS in Supabase

### Alerts

- Error rate > 1%
- P99 latency > 5s
- Quota approaching limit
- Security violations
- Deployment failures

## Summary

This three-layer architecture:

1. **Keeps concerns separated** - CLI, Worker, Storage
2. **Maintains security** - End-to-end encryption
3. **Enables scaling** - Each layer scales independently
4. **Supports evolution** - Self-updating capability
5. **Ensures reliability** - Monitoring & failover
6. **Facilitates development** - Clear boundaries & interfaces

The architecture is stable and extensible. All changes should maintain these three layers and security standards.
