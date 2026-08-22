# AI Integration: NVIDIA Nemotron

## Overview

The system integrates NVIDIA Nemotron 3 Ultra for AI-powered features (code fixing, explanation, generation, error diagnosis).

## API Details

### Endpoint

```
https://integrate.api.nvidia.com/v1/chat/completions
```

### Authentication

```
Authorization: Bearer <NVIDIA_API_KEY>
```

### Request Format

```json
{
  "model": "nvidia/nemotron-3-ultra",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful coding assistant..."
    },
    {
      "role": "user",
      "content": "explain this code..."
    }
  ],
  "temperature": 0.7,
  "max_tokens": 2048,
  "stream": false
}
```

### Response Format

```json
{
  "id": "cmpl-...",
  "object": "text_completion",
  "created": 1691234567,
  "model": "nvidia/nemotron-3-ultra",
  "choices": [
    {
      "text": "AI response here...",
      "index": 0,
      "finish_reason": "stop",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 250,
    "total_tokens": 300
  }
}
```

---

## Commands Using Nemotron

### warnetech ai "<prompt>"

**System Prompt:**

```
You are Claude, an AI assistant for the Warnetech command-line system.
You help developers with:
- Understanding and explaining code
- Fixing bugs and errors
- Generating scripts and commands
- Optimizing performance
- Security reviews

Provide concise, actionable responses.
For code, use syntax highlighting.
For errors, explain the root cause and solution.
```

**Flow:**

1. User provides prompt
2. CLI sends to Worker (encrypted)
3. Worker calls NVIDIA API
4. Worker streams/buffers response
5. CLI displays formatted output

---

### warnetech fix "<file_path>"

**System Prompt:**

```
Analyze the provided code and:
1. Identify any bugs, issues, or potential problems
2. Suggest specific fixes with code examples
3. Explain why each fix is needed
4. Rate severity: critical | high | medium | low

Focus on:
- Security vulnerabilities
- Performance issues
- Code quality
- Best practices
```

**Example:**

```bash
$ warnetech fix "buggy_script.sh"
✓ Analyzing script.sh...

Issues Found:
1. [CRITICAL] Unquoted variables may cause word splitting
   - Line 15: rm -rf $dir  →  rm -rf "$dir"

2. [HIGH] Missing error handling
   - Line 8: curl $url  →  curl "$url" || exit 1

3. [MEDIUM] Hardcoded paths
   - Line 3: /tmp/data  →  ${TMPDIR}/data

Apply fixes? (y/n)
```

---

### warnetech explain "<file_path>"

**System Prompt:**

```
Explain the provided code in detail:
1. Purpose and high-level overview
2. Key functions and their roles
3. Data flow and control flow
4. Dependencies and integrations
5. Security considerations if applicable

Use clear language suitable for someone learning to code.
Break down complex concepts.
```

---

### warnetech help --error "<error_message>"

**System Prompt:**

```
A user encountered an error in the Warnetech CLI system:
"${error_message}"

Provide:
1. Explanation of what went wrong
2. Likely causes
3. Step-by-step troubleshooting
4. Suggested commands to resolve
5. Prevention tips for the future
```

**Example:**

```bash
$ warnetech ai "some prompt" && echo OK
✗ Error: connection timeout

$ warnetech help --error "connection timeout"
✓ AI Troubleshooting: Connection Timeout

Explanation:
The CLI couldn't reach the Worker within 30 seconds.

Common Causes:
1. Network connectivity issue
2. Worker is down or overloaded
3. Rate limit hit (pauses requests)
4. API timeout from NVIDIA

Troubleshooting:
1. Check connection: ping 8.8.8.8
2. Check Worker: warnetech status
3. Check quotas: warnetech quota check
4. Retry: warnetech ai "..." --timeout 60

Prevention:
- Use --stream for long operations
- Use --timeout based on expected duration
- Monitor quotas with: warnetech quota check
```

---

## Streaming Support

### Streaming Reasoning Tokens

For complex queries, enable streaming to see reasoning tokens in real-time.

**Request:**

```json
{
  "stream": true,
  "model": "nvidia/nemotron-3-ultra",
  "messages": [...]
}
```

**Response Stream:**

```
data: {"choices":[{"delta":{"content":"The"}}]}
data: {"choices":[{"delta":{"content":" first"}}]}
data: {"choices":[{"delta":{"content":" step"}}]}
...
data: [DONE]
```

**CLI Implementation:**

```bash
warnetech ai "explain quantum computing" --stream
> Starting stream...
The first step in understanding quantum computing is...
[reasoning tokens displayed in real-time]
```

---

## Prompt Optimization

### AST Mutation Engine

The Worker performs automated prompt optimization using Abstract Syntax Tree mutations.

**Optimization Strategy:**

1. **Conciseness**: Remove redundant words
2. **Clarity**: Add specificity and context
3. **Structure**: Reorganize for better understanding
4. **Examples**: Add relevant examples if missing
5. **Constraints**: Add helpful constraints (language, format)

**Example Mutations:**

```
Before: "explain code"
After: "Explain this code in 2-3 sentences, focusing on the main logic"

Before: "fix this"
After: "Identify the bug, explain why it's wrong, and provide the fix"

Before: "generate script"
After: "Generate a bash script for backing up files to S3, with error handling"
```

**Implementation:**

```javascript
function optimizePrompt(userPrompt, context) {
  let optimized = userPrompt;

  // Add context if available
  if (context.language) {
    optimized = `[${context.language}]\n${optimized}`;
  }

  // Add format constraint if applicable
  if (context.wantCode) {
    optimized += "\n\nProvide code only, no explanation.";
  }

  // Ensure completeness
  if (!optimized.includes("?") && !optimized.endsWith(".")) {
    optimized += ".";
  }

  return optimized;
}
```

---

## Error Handling via AI

### Nemotron Error Explanations

When a command fails, offer AI-powered explanation.

**Flow:**

1. Command fails with error message
2. CLI catches error
3. CLI offers: `Run 'warnetech help --error "message"' for explanation`
4. User accepts or declines
5. If yes, send error to Worker
6. Worker calls NVIDIA with error context
7. Display formatted explanation

**Example:**

```bash
$ warnetech gh-push "fix: bug"
✗ Error: Repository not found
The repository at origin may have been deleted or made private.

Get help: warnetech help --error "Repository not found"
```

---

## Rate Limiting & Quotas

### NVIDIA Quotas

Track usage to avoid hitting API limits.

**Stored in Supabase:**

```sql
CREATE TABLE nvidia_quotas (
  user_id TEXT,
  model TEXT,
  tokens_used INT,
  requests_count INT,
  daily_limit INT,
  monthly_limit INT,
  reset_at TIMESTAMP
);
```

**Check Before Request:**

```javascript
function checkQuota(userId, tokensNeeded) {
  const quota = getQuota(userId);
  if (quota.tokens_used + tokensNeeded > quota.monthly_limit) {
    throw new Error("Monthly token limit reached");
  }
  return true;
}
```

---

## Model Selection

### Nemotron 3 Ultra (Default)

- Reasoning capability: Excellent
- Code generation: Excellent
- Speed: Fast
- Cost: Medium

**Use for:** Code analysis, debugging, complex explanations

### Fallback Models

If Nemotron is unavailable:

- Claude (via Anthropic API)
- GPT-4 (via OpenAI)
- Local LLM (Ollama)

---

## Security in AI Integration

### No Sensitive Data

- Never send passwords, tokens, secrets to NVIDIA
- Remove API keys from code samples
- Redact PII from logs
- Use data tier classification

### Prompt Injection Prevention

```javascript
function sanitizePrompt(prompt) {
  // Remove common injection patterns
  prompt = prompt.replace(/[^a-zA-Z0-9\s\n"'.,!?-]/g, " ");

  // Limit length
  if (prompt.length > 5000) {
    prompt = prompt.substring(0, 5000);
  }

  return prompt;
}
```

### Model Output Validation

```javascript
function validateResponse(response) {
  // Check for suspicious patterns
  if (response.includes("API key")) {
    throw new Error("Response contains sensitive data");
  }

  // Verify response isn't truncated
  if (response.endsWith("...")) {
    // Handle truncation
  }

  return response;
}
```

---

## Testing

### Unit Tests

- Test prompt optimization
- Test response parsing
- Test error handling
- Test streaming

### Integration Tests

- End-to-end AI request
- Test rate limiting
- Test fallback models
- Test large responses

### Load Tests

- 100 concurrent requests
- Monitor token usage
- Check rate limit behavior
