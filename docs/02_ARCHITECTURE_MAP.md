# Architecture Map

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Termux CLI (Node.js)                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Command Router                                          │ │
│  │  - warnetech ai "<prompt>"                                 │ │
│  │  - warnetech fix "<file>"                                  │ │
│  │  - warnetech explain "<file>"                              │ │
│  │  - warnetech gh-open "<repo>"                              │ │
│  │  - warnetech gh-push "<message>"                           │ │
│  │  - warnetech status                                         │ │
│  │  - warnetech evolve                                         │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
            ↓ (HTTPS + AES-256-GCM)
┌─────────────────────────────────────────────────────────────┐
│          Cloudflare Worker (Request Handler)                 │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Security Layer                                          │ │
│  │  - Validate API_KEY                                     │ │
│  │  - Decrypt request (AES-256-GCM)                        │ │
│  │  - Anti-tamper checks                                   │ │
│  │  - Data tier enforcement                                │ │
│  └─────────────────────────────────────────────────────────┘ │
│                         ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Command Dispatcher                                      │ │
│  │  - ai.js (NVIDIA Nemotron)                              │ │
│  │  - gh.js (GitHub operations)                            │ │
│  │  - sys.js (System operations)                           │ │
│  └─────────────────────────────────────────────────────────┘ │
│                         ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  External Integrations                                   │ │
│  │  - NVIDIA API (Nemotron 3 Ultra)                        │ │
│  │  - GitHub API                                           │ │
│  │  - Cloudflare D1 (cache)                                │ │
│  │  - Cloudflare R2 (backups)                              │ │
│  │  - Supabase Postgres 17                                 │ │
│  │  - Cloudflare KV (rate limits)                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
            ↓ (HTTPS + AES-256-GCM)
┌─────────────────────────────────────────────────────────────┐
│                 Termux CLI (Response Handler)                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Response Processing                                     │ │
│  │  - Decrypt response                                     │ │
│  │  - Validate integrity                                   │ │
│  │  - Format output                                        │ │
│  │  - Error handling via Nemotron                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Request Flow

1. User types CLI command in Termux
2. CLI parses command & arguments
3. CLI loads config from ~/.claude-cli/config.json
4. CLI encrypts request (AES-256-GCM)
5. CLI sends HTTPS POST to Worker
6. Worker validates API_KEY
7. Worker decrypts request
8. Worker dispatches to appropriate handler

### Response Flow

1. Handler processes command
2. Handler prepares JSON response
3. Handler encrypts response
4. Worker sends encrypted response
5. CLI receives & decrypts response
6. CLI displays formatted output

## Component Responsibilities

### warnetech_cli_legacy/warnetech

- Command parsing & routing
- Request encryption
- Config management
- Output formatting
- Error handling

### worker/index.js

- HTTP server
- Security layer (validation, decryption)
- Command dispatching
- Response preparation

### worker/commands/

- **ai.js**: NVIDIA Nemotron integration, streaming, reasoning tokens
- **gh.js**: GitHub API operations (open, push, pull, PR review)
- **sys.js**: System operations (status, quotas, logs)

### worker/utils/

- **validate.js**: Crypto validation, anti-tamper checks, data tier enforcement
- **respond.js**: JSON response formatting, error handling
- **nemotron.js**: NVIDIA API client, prompt optimization

## Security Architecture

### Encryption

- Primary: AES-256-GCM (AEAD)
- Fallback: ChaCha20-Poly1305
- Key Derivation: Argon2id
- Post-Quantum: ML-KEM (Kyber) handshake patterns

### Authentication

- API_KEY validation on every request
- Signature verification for integrity
- Rate limiting via Cloudflare KV

### Data Protection

- Tier 1: Highly Sensitive (encrypted at rest + in transit)
- Tier 2: Sensitive (encrypted in transit)
- Tier 3: Public (no encryption required)

### Audit Logging

- WORM (Write-Once-Read-Many) storage in R2
- Row-Level Security (RLS) in Supabase
- Sensitive data never logged in plaintext

## Evolution & Self-Update

The system supports self-updating via ASAEAI patterns:

- **Sandbox Synthesis**: Test code changes in isolated environment
- **Automated Verification**: Validate changes before deployment
- **Atomic Deployment**: Deploy or rollback as single unit
- **AST Mutation Engine**: Generate and apply code transformations

Command: `warnetech evolve`
