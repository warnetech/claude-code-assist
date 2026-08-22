# Code Standards Quick Reference

This file captures the core standards Claude should follow when generating code.

## General Standards

### Code Quality

- ✅ **Use clear, modular code**
  - One responsibility per function
  - Self-documenting variable names
  - Reusable utility functions

- ✅ **Avoid unnecessary dependencies**
  - Don't add packages without justification
  - Prefer built-in Node.js modules
  - Use Cloudflare Worker built-ins

- ✅ **Keep everything lightweight**
  - Small bundle size
  - Fast execution
  - Minimal memory usage
  - Cloudflare free tier compatible

### Technology Choices

- ✅ **Prefer pure JavaScript for Worker code**
  - No TypeScript (adds complexity)
  - No build step required
  - Direct Node.js APIs
  - Cloudflare native support

- ✅ **Prefer Bash for Termux CLI**
  - Lightweight & portable
  - Works anywhere on mobile
  - No runtime dependencies
  - Direct system integration

  (Note: Termux CLI scaffolding uses Node.js/Commander for now, can be converted to Bash)

---

## Cloudflare Worker Standards

These standards apply to `worker/` code.

### Authentication & Validation

```javascript
// ✅ DO: Always validate Authorization header
export async function handleRequest(request) {
  const authHeader = request.headers.get("authorization");
  if (!authHeader) {
    return respondError("Missing authorization", 401);
  }

  const valid = await validateAuth(authHeader);
  if (!valid) {
    return respondError("Invalid credentials", 401);
  }

  // Process request
}

// ❌ DON'T: Skip validation
export async function handleRequest(request) {
  // No auth check!
  return processRequest(request);
}
```

### Response Format

```javascript
// ✅ DO: Always return JSON
return new Response(
  JSON.stringify({
    ok: true,
    data: result,
    timestamp: new Date().toISOString(),
  }),
  {
    status: 200,
    headers: { "Content-Type": "application/json" },
  },
);

// ❌ DON'T: Return plain text or mix formats
return new Response("success");
```

### Error Handling

```javascript
// ✅ DO: Handle errors gracefully
try {
  return await processCommand(request);
} catch (error) {
  console.error("Error:", error);
  return respondError(
    error.message || "Internal error",
    error.statusCode || 500,
  );
}

// ❌ DON'T: Let errors crash
try {
  return await processCommand(request);
} catch (error) {
  throw error; // Crashes worker!
}
```

### Endpoint Design

```javascript
// ✅ DO: Keep endpoints simple and predictable
// POST /api/command with clear payload
{
  command: 'ai' | 'gh' | 'sys',
  args: string[],
  encrypted: boolean
}

// GET /health for status
// POST /api/authenticate for auth negotiation

// ❌ DON'T: Create complex nested routes
// GET /api/v1/commands/ai/prompts/123/responses?filter=...
```

### Code Structure

```javascript
// ✅ DO: Clear separation of concerns
// worker/index.js - routing
// worker/commands/ai.js - handler
// worker/utils/validate.js - validation
// worker/utils/nemotron.js - API client

// ❌ DON'T: Mix everything in one file
// All handlers, validation, API calls in index.js
```

---

## Termux CLI Standards

These standards apply to `warnetech_cli_legacy/` code.

### Command Design

```bash
# ✅ DO: Short, intuitive commands
warnetech ai "prompt"
warnetech fix "file.js"
warnetech gh-push "message"
warnetech status
warnetech help

# ❌ DON'T: Complex or ambiguous commands
warnetech artificial-intelligence-prompt-sender "prompt"
warnetech file-repair file.js
warnetech github-push-changes "message"
```

### Output Format

```bash
# ✅ DO: Clean, readable output
$ warnetech status
✓ CLI Version: 1.0.0
✓ Worker: Connected
✓ Quotas: 45/100 API calls (45%)
✓ Sync: 2026-08-05 10:15:00

# ✅ DO: Use symbols for clarity
✓ Success indicator
✗ Error indicator
> Info indicator
? Question indicator
⚠ Warning indicator

# ❌ DON'T: Verbose or unclear output
Status: OK, Version: 1.0.0, Worker connection: established, etc.
```

### Error Messages

```bash
# ✅ DO: Clear error explanation
$ warnetech ai "prompt"
✗ Error: API_KEY not found in config
  Run: warnetech init
  For help: warnetech help --error "API_KEY not found"

# ✅ DO: Suggest next steps
✗ Failed to connect to Worker
  Check: warnetech status
  Retry: warnetech ai "prompt" --timeout 60

# ❌ DON'T: Cryptic errors
Error: ECONNREFUSED
Error code: -2
Connection failed
```

### Command Help

```bash
# ✅ DO: Provide clear help
$ warnetech help ai
Usage: warnetech ai "<prompt>"

Send a prompt to Claude (NVIDIA Nemotron) for AI assistance.

Options:
  --stream         Stream reasoning tokens in real-time
  --timeout <sec>  Set timeout in seconds (default: 30)
  --model <model>  Specify model (default: nemotron-3-ultra)

Examples:
  warnetech ai "explain this code"
  warnetech ai "generate a bash script" --stream

# ❌ DON'T: Minimal or unclear help
$ warnetech help ai
ai - send prompt
```

---

## Implementation Patterns

### Worker: Validation Pattern

```javascript
// worker/utils/validate.js
async function validateRequest(body, headers, env) {
  // 1. Check authorization
  const auth = headers.get("authorization");
  if (!auth) return { ok: false, error: "Missing auth" };

  // 2. Check required fields
  if (!body.command) return { ok: false, error: "Missing command" };

  // 3. Validate command
  const validCommands = ["ai", "gh", "sys"];
  if (!validCommands.includes(body.command)) {
    return { ok: false, error: "Invalid command" };
  }

  return { ok: true, command: body.command, args: body.args };
}
```

### Worker: Response Pattern

```javascript
// worker/utils/respond.js
function respondSuccess(data, command) {
  return new Response(
    JSON.stringify({
      ok: true,
      command,
      data,
      timestamp: new Date().toISOString(),
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

function respondError(message, statusCode = 500) {
  return new Response(
    JSON.stringify({
      ok: false,
      error: message,
      timestamp: new Date().toISOString(),
    }),
    { status: statusCode, headers: { "Content-Type": "application/json" } },
  );
}
```

### CLI: Command Pattern

```bash
#!/bin/bash
# warnetech_cli_legacy/commands/ai.sh

usage() {
  cat <<EOF
Usage: warnetech ai "<prompt>"

Send prompt to Claude for AI assistance.

Options:
  --stream         Stream reasoning tokens
  --timeout N      Timeout in seconds
  --model MODEL    AI model to use

Examples:
  warnetech ai "explain quantum computing"
  warnetech ai "fix this code" --stream

EOF
}

main() {
  if [[ $# -eq 0 ]]; then
    usage
    exit 1
  fi

  local prompt="$1"
  shift

  # Process options
  local stream=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --stream) stream=true; shift ;;
      --timeout) timeout="$2"; shift 2 ;;
      *) echo "Unknown option: $1"; exit 1 ;;
    esac
  done

  # Send to Worker
  send_to_worker "ai" "$prompt"
}

main "$@"
```

---

## Common Mistakes to Avoid

### Worker Mistakes

```javascript
// ❌ Missing auth check
export async function handle(request) {
  // No validation!
  return processRequest(request);
}

// ❌ No error handling
export async function handle(request) {
  const result = JSON.parse(request.body);
  return new Response(result.data); // Crashes if parse fails
}

// ❌ Wrong content type
return new Response(JSON.stringify(data)); // Missing header
// Should include: headers: { 'Content-Type': 'application/json' }

// ❌ Logging secrets
console.log("API Key:", apiKey); // Never!
```

### CLI Mistakes

```bash
# ❌ Unclear commands
warnetech generateaicodefix "file.js"
warnetech gitpushchanges "message"

# ❌ Poor error output
Error: connection timeout
(no suggestion for next step)

# ❌ No progress feedback
# User doesn't know what's happening
warnetech ai "prompt"
(waits silently for 30 seconds)

# ❌ Inconsistent output
Output changes format between commands
Some commands show "OK", others show "success", others show nothing
```

---

## Checklist Before Committing

Use this checklist before committing code:

### Worker Code

- [ ] Auth validation on all endpoints
- [ ] All responses are JSON
- [ ] All errors caught and handled
- [ ] No secrets in code
- [ ] No console.log of sensitive data
- [ ] Modular: each handler in separate file
- [ ] Tests included
- [ ] Lint passes: `npm run lint`

### CLI Code

- [ ] Commands are short (1-2 words)
- [ ] Output is clean & readable
- [ ] Errors explain what went wrong
- [ ] Help text clear
- [ ] Suggest next steps for errors
- [ ] No hardcoded secrets
- [ ] Works in Termux
- [ ] Tests included

### Both

- [ ] No unnecessary dependencies
- [ ] Code is lightweight
- [ ] Comments only for non-obvious logic
- [ ] Variable names are clear
- [ ] Follows modular patterns
- [ ] Commit message clear
- [ ] Documentation updated
- [ ] Passes all tests

---

## Quick Reference

### Auth Pattern

```javascript
const auth = headers.get("authorization");
if (!auth) return respondError("Unauthorized", 401);
```

### JSON Response Pattern

```javascript
return new Response(JSON.stringify({ ok: true, data }), {
  headers: { "Content-Type": "application/json" },
});
```

### Error Handling Pattern

```javascript
try {
  // operation
} catch (error) {
  return respondError(error.message, 500);
}
```

### CLI Error Pattern

```bash
echo "✗ Error: clear explanation"
echo "  Next step: warnetech help command"
exit 1
```

### Command Pattern

```javascript
// worker/commands/cmd.js
async function handleCmd(args, env) {
  // Validate args
  if (!args[0]) throw new Error("Argument required");

  // Process
  const result = await doWork(args);

  // Return result
  return result;
}

export default handleCmd;
```

---

## When in Doubt

1. **Check existing code** - Follow established patterns
2. **Read CLAUDE.md** - For architectural guidance
3. **Read 04_CODE_STANDARDS.md** - For detailed standards
4. **Keep it simple** - Simpler is usually better
5. **Test it** - Write tests before committing
6. **Ask user** - If uncertain about approach

---

## Example: Good Code

### Worker Example

```javascript
// worker/commands/ai.js
import nemotron from "../utils/nemotron.js";

async function handleAi(args, env) {
  // Validate
  if (!args || args.length === 0) {
    throw new Error("Prompt required");
  }

  // Process
  const prompt = args[0];
  const response = await nemotron.chat(prompt, env.NVIDIA_API_KEY);

  // Return
  return {
    response: response.text,
    tokens: response.tokens,
    model: "nemotron-3-ultra",
  };
}

export default handleAi;
```

### CLI Example

```bash
#!/bin/bash
# Shows clear output and error handling

if [[ ! -f ~/.claude-cli/config.json ]]; then
  echo "✗ Error: Configuration not found"
  echo "  Run: warnetech init"
  exit 1
fi

echo "✓ Sending prompt to Claude..."
response=$(curl -s -X POST \
  -H "Authorization: Bearer $API_KEY" \
  -d "$(json_encode)" \
  https://worker.example.workers.dev/api/command)

if [[ $? -ne 0 ]]; then
  echo "✗ Error: Connection failed"
  echo "  Check: warnetech status"
  exit 1
fi

echo "$response" | jq .
echo "✓ Complete"
```

---

**Follow these standards consistently. They keep the codebase clean, secure, and maintainable.**
