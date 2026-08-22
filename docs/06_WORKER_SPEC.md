# Cloudflare Worker Specification

## Overview

The Worker acts as the secure gateway between Termux CLI and external APIs (NVIDIA, GitHub, Warnetech).

## Endpoints

### POST /api/command

Main command processing endpoint.

**Request:**

```
Headers:
  Content-Type: application/json
  X-API-Key: <api_key_hash>
  X-Request-ID: <uuid>
  X-Timestamp: <iso8601>

Body:
{
  command: 'ai' | 'gh' | 'sys',
  args: string[],
  encrypted: boolean,
  signature: string,
  payload: string (base64 if encrypted)
}
```

**Response (Success):**

```json
{
  "ok": true,
  "command": "ai",
  "data": {/* result */},
  "encrypted": true,
  "signature": "hmac_signature",
  "timestamp": "2026-08-05T10:15:00Z"
}
```

**Response (Error):**

```json
{
  "ok": false,
  "error": "descriptive message",
  "code": "ERROR_CODE",
  "timestamp": "2026-08-05T10:15:00Z"
}
```

---

### GET /health

Health check endpoint.

**Response:**

```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2026-08-05T10:15:00Z"
}
```

---

### POST /api/authenticate

Initial authentication & key negotiation.

**Request:**

```json
{
  "api_key": "public_key_hash",
  "handshake": "ml_kem_public_key"
}
```

**Response:**

```json
{
  "ok": true,
  "session_token": "encrypted_token",
  "handshake_response": "ml_kem_response",
  "expires_in": 3600
}
```

---

### POST /api/hotload

Hot reload & patch deployment endpoint.

**Request:**

```json
{
  action: 'patch' | 'rollback' | 'status',
  patch_id: 'uuid',
  code: 'base64_encoded_code' (if patch)
}
```

**Response:**

```json
{
  ok: true,
  deployment_id: 'uuid',
  status: 'deployed' | 'rolled_back',
  timestamp: '2026-08-05T10:15:00Z'
}
```

---

## Command Handlers

### ai.js

Handles NVIDIA Nemotron API integration.

**Input:**

```javascript
{
  command: 'ai',
  args: ['what is rust?'],
  stream: false,
  model: 'nemotron-3-ultra'
}
```

**Process:**

1. Extract prompt from args[0]
2. Optimize prompt via AST mutation (optional)
3. Call NVIDIA API at https://integrate.api.nvidia.com/v1/chat/completions
4. Handle streaming if requested
5. Format response

**Output:**

```javascript
{
  response: 'AI response text',
  reasoning_tokens: 1250,
  tokens_used: { input: 50, output: 250 },
  model: 'nemotron-3-ultra'
}
```

**Error Handling:**

- Rate limit exceeded: 429
- Invalid API key: 401
- Prompt timeout: 504
- Return user-friendly error for CLI to show

---

### gh.js

Handles GitHub API operations.

**Commands:**

- `gh-open <repo>`: Get repo info, return Claude link
- `gh-push`: Commit & push (requires GitHub auth)
- `gh-pull`: Pull latest

**Input:**

```javascript
{
  command: 'gh',
  action: 'open' | 'push' | 'pull',
  args: ['tewartech-node/claude-command-cli', 'commit message'],
  github_token: 'gh_token' (from config)
}
```

**Process:**

1. Validate GitHub token
2. Verify repository access
3. Perform action (read/write)
4. Return results

**Output for gh-open:**

```javascript
{
  repo: 'tewartech-node/claude-command-cli',
  url: 'https://github.com/tewartech-node/claude-command-cli',
  claude_url: 'https://claude.ai/new?repo=https://github.com/tewartech-node/claude-command-cli',
  stars: 42,
  description: 'Termux CLI for Claude'
}
```

---

### sys.js

Handles system operations (status, quotas, sync, etc).

**Commands:**

- `status`: Get system status
- `quota`: Check quota usage
- `sync`: Sync baselines & signatures
- `detect-anomalies`: Run anomaly detection
- `rollup`: Perform quota rollup

**Input:**

```javascript
{
  command: 'sys',
  action: 'status' | 'quota' | 'sync' | 'detect-anomalies' | 'rollup',
  args: []
}
```

**Output for status:**

```javascript
{
  status: 'healthy',
  version: '1.0.0',
  uptime: 3600,
  worker_url: 'https://worker.example.workers.dev',
  services: {
    nvidia_api: 'ok',
    github_api: 'ok',
    d1: 'ok',
    r2: 'ok',
    supabase: 'ok',
    kv: 'ok'
  }
}
```

---

## Security Layer

### Validation (validate.js)

**API Key Validation:**

```javascript
function validateApiKey(key) {
  const stored = ENVIRONMENT.API_KEY_HASH;
  return crypto.timingSafeEqual(Buffer.from(hashKey(key)), Buffer.from(stored));
}
```

**Request Signature:**

```javascript
function verifySignature(payload, signature, secret) {
  const hmac = crypto
    .createHmac("sha256", secret)
    .update(payload)
    .digest("hex");
  return hmac === signature;
}
```

**Anti-Tamper Checks:**

- Verify X-Request-ID not seen before (prevent replay)
- Check X-Timestamp within 5 minutes
- Verify payload integrity with HMAC
- Check data tier compliance

**Data Tier Enforcement:**

```javascript
const TIERS = {
  TIER_1: { encrypt_at_rest: true, encrypt_in_transit: true },
  TIER_2: { encrypt_at_rest: false, encrypt_in_transit: true },
  TIER_3: { encrypt_at_rest: false, encrypt_in_transit: false },
};
```

---

### Encryption/Decryption (validate.js)

**Decrypt Request:**

```javascript
async function decryptRequest(payload, key) {
  const { ciphertext, iv, authTag, salt } = payload;
  const derivedKey = await deriveKey(key, salt);
  const decipher = crypto.createDecipheriv("aes-256-gcm", derivedKey, iv);
  decipher.setAuthTag(authTag);
  return decipher.update(ciphertext) + decipher.final();
}
```

**Encrypt Response:**

```javascript
async function encryptResponse(data, key) {
  const iv = crypto.randomBytes(12);
  const salt = crypto.randomBytes(16);
  const derivedKey = await deriveKey(key, salt);
  const cipher = crypto.createCipheriv("aes-256-gcm", derivedKey, iv);
  const ciphertext = cipher.update(JSON.stringify(data)) + cipher.final();
  return {
    ciphertext,
    iv: iv.toString("base64"),
    authTag: cipher.getAuthTag().toString("base64"),
    salt: salt.toString("base64"),
  };
}
```

---

### Response Formatting (respond.js)

**Success Response:**

```javascript
function respondSuccess(data, command) {
  return {
    ok: true,
    command,
    data,
    timestamp: new Date().toISOString(),
  };
}
```

**Error Response:**

```javascript
function respondError(error, statusCode = 500) {
  return {
    ok: false,
    error: error.message,
    code: error.code || "INTERNAL_ERROR",
    timestamp: new Date().toISOString(),
  };
}
```

---

## Environment Variables

```
ENVIRONMENT:
  API_KEY_HASH = hash of CLI API key
  WORKER_ENV = 'production' | 'staging' | 'development'

SERVICES:
  NVIDIA_API_KEY = NVIDIA Nemotron API key
  GITHUB_TOKEN = GitHub API token (optional)

CLOUDFLARE:
  D1_ID = D1 database ID
  R2_BUCKET = R2 bucket name
  KV_NAMESPACE = KV namespace ID

SUPABASE:
  SUPABASE_URL = Postgres connection string
  SUPABASE_KEY = Supabase API key

RATES:
  RATE_LIMIT_PER_MINUTE = 100
  RATE_LIMIT_PER_DAY = 1000
```

---

## Deployment

### wrangler.toml

```toml
name = "claude-command-cli-worker"
main = "index.js"
compatibility_date = "2026-08-01"

[env.production]
routes = [
  { pattern = "*.workers.dev", zone_name = "workers.dev" }
]

[env.staging]
routes = [
  { pattern = "staging-*.workers.dev", zone_name = "workers.dev" }
]
```

### Deployment Steps

1. `wrangler publish` - Deploy Worker
2. `wrangler secret put NVIDIA_API_KEY` - Set secrets
3. `curl https://your-worker.workers.dev/health` - Verify
4. Gradually route traffic (canary deployment)
5. Monitor error rates & latency

---

## Monitoring & Logging

### Metrics

- Request count (by endpoint, by status)
- Latency (p50, p95, p99)
- Error rates
- NVIDIA API quota usage
- Rate limit hits

### Logging

- All requests logged (no plaintext secrets)
- Errors logged with stack traces
- Audit log for security events
- WORM storage in R2
- RLS in Supabase for log access
