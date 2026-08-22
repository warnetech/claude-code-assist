# Code Standards

## General Principles

- Modular architecture: each responsibility in separate file
- Default to no comments: only explain WHY for non-obvious logic
- Trust internal code; validate only at system boundaries
- No premature abstractions: three similar lines > one abstraction
- Security first: crypto standards, no plaintext secrets
- Clean error handling: meaningful messages for users

## File Organization

### Directory Structure

```
worker/
├── index.js           # HTTP handler, routing
├── commands/          # Command implementations
│   ├── ai.js
│   ├── gh.js
│   └── sys.js
└── utils/             # Shared utilities
    ├── validate.js    # Validation & security
    ├── respond.js     # Response formatting
    └── nemotron.js    # NVIDIA API client

warnetech_cli_legacy/
├── warnetech             # Main CLI entrypoint
└── config.json        # Runtime config

scripts/
├── claude-open.sh     # Opens Claude
├── gh-push.sh         # Git automation
└── gh-pull.sh
```

## Naming Conventions

### Files & Directories

- Use snake_case for files: `nemotron.js`, `anti_tamper.js`
- Use CAPS for constants: `MAX_RETRIES`, `API_KEY`
- Use camelCase for functions/classes: `encryptRequest()`, `CommandRouter`

### Variables

- `const` by default, `let` if reassignment needed
- Avoid `var`
- Meaningful names: `encryptedPayload` not `x`
- Prefix booleans with `is`/`has`: `isValid`, `hasError`

## Error Handling

### Termux CLI

```javascript
try {
  const response = await sendToWorker(command);
  console.log(response);
} catch (error) {
  console.error(`Error: ${error.message}`);
  process.exit(1);
}
```

### Cloudflare Worker

```javascript
try {
  const decrypted = await decrypt(request);
  return handleCommand(decrypted);
} catch (error) {
  return respondWithError(error, 400);
}
```

### User-Facing Errors

- Be specific: not "error" but "API_KEY not found in config"
- Suggest next steps: "Run: warnetech --init"
- Use Nemotron for complex errors: `warnetech help <error>`

## Cryptography Standards

### AES-256-GCM (Primary)

```javascript
const algorithm = "aes-256-gcm";
const key = deriveKey(password, salt, { n: 65536 }); // Argon2id
const iv = crypto.randomBytes(12);
const cipher = crypto.createCipheriv(algorithm, key, iv);
```

### ChaCha20-Poly1305 (Fallback)

```javascript
const algorithm = "chacha20-poly1305";
const cipher = crypto.createCipheriv(algorithm, key, nonce);
```

### Never

- Store plaintext secrets
- Log encryption keys
- Send unencrypted sensitive data
- Use weak random (always use crypto.randomBytes)

## Security Practices

### Input Validation

```javascript
function validateApiKey(key) {
  if (!key || typeof key !== "string") throw new Error("Invalid API_KEY");
  if (key.length < 32) throw new Error("API_KEY too short");
  return key;
}
```

### Rate Limiting

- Use Cloudflare KV namespace
- Key: `rate_limit:{userId}:{endpoint}`
- Value: `{ count, expiry }`
- Check before processing request

### Data Tier Enforcement

```javascript
const TIERS = {
  TIER_1: "highly_sensitive", // encrypt at rest + in transit
  TIER_2: "sensitive", // encrypt in transit only
  TIER_3: "public", // no encryption required
};
```

## API Response Format

### Success

```javascript
{
  ok: true,
  data: { /* command result */ },
  timestamp: new Date().toISOString()
}
```

### Error

```javascript
{
  ok: false,
  error: 'descriptive error message',
  code: 'ERROR_CODE',
  timestamp: new Date().toISOString()
}
```

## Termux CLI Output

### Commands

- Status messages: `✓ Task completed`
- Errors: `✗ Error: reason`
- Info: `> This is information`
- Prompts: `? Question: `

### Formatting

```javascript
console.log("✓ Request sent");
console.error("✗ Failed: details");
console.log("> Status: active");
```

## Worker Endpoints

### Command Structure

```
POST /api/command
Content-Type: application/json
X-API-Key: <api_key>

{
  command: 'ai',
  args: ['<prompt>'],
  encrypted: true,
  signature: '<hmac_signature>'
}
```

### Response Structure

```
{
  ok: true,
  command: 'ai',
  data: { /* result */ },
  encrypted: true,
  signature: '<hmac_signature>'
}
```

## Testing Standards

### Unit Tests

- One test file per module
- Test success path and error cases
- Use meaningful test names
- Mock external APIs

### Integration Tests

- Test full workflow: CLI → Worker → API → CLI
- Test encryption/decryption round-trip
- Test error handling end-to-end

### Test Naming

```javascript
describe("AES-256-GCM Encryption", () => {
  it("encrypts and decrypts plaintext", () => {
    /* ... */
  });
  it("rejects invalid key", () => {
    /* ... */
  });
  it("validates authentication tag", () => {
    /* ... */
  });
});
```

## Git Commit Standards

### Commit Messages

- Format: `<type>: <description>`
- Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- Examples:
  - `feat: add warnetech ai command`
  - `fix: AES-256-GCM nonce handling`
  - `test: add integration tests for gh-push`
  - `docs: update architecture diagram`

### Commits

- One feature per commit
- Atomic commits (complete, working code)
- Include test updates in same commit
- Never commit secrets or .env files

## Documentation Standards

### Code Comments

- Explain WHY, not WHAT (code shows what)
- Only for non-obvious logic
- Keep comments short: one line max
- Keep comments near code they explain

### Function Documentation

```javascript
// Encrypts plaintext using AES-256-GCM.
// Returns { ciphertext, iv, authTag } as base64.
function encryptAES(plaintext, key, nonce = null) {
  // implementation
}
```

### README in Each Directory

- Purpose of the directory
- Files and their responsibilities
- How to use/integrate
- Any special requirements
