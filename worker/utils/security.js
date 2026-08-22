// Advanced security features: anti-tamper, data tiers, rate limiting

// Data classification tiers
const DATA_TIERS = {
  TIER_1: {
    name: "Highly Sensitive",
    encrypted_at_rest: true,
    encrypted_in_transit: true,
    access_logging: true,
    examples: "API keys, passwords, tokens",
  },
  TIER_2: {
    name: "Sensitive",
    encrypted_at_rest: false,
    encrypted_in_transit: true,
    audit_logging: true,
    examples: "User code, prompts, analysis results",
  },
  TIER_3: {
    name: "Public",
    encrypted_at_rest: false,
    encrypted_in_transit: false,
    public_logging: true,
    examples: "Help text, status info, version numbers",
  },
};

// Anti-tamper checks
function validateRequestStructure(request) {
  // Check if it's a plain object (not array, null, or other types)
  if (!request || typeof request !== "object" || Array.isArray(request)) {
    throw new Error("Invalid request structure");
  }

  // Check for required fields
  if (!request.command && !request.encrypted_data) {
    throw new Error("Missing command or encrypted_data");
  }

  // If encrypted, check signature
  if (request.encrypted_data && !request.signature) {
    throw new Error("Encrypted request missing signature");
  }

  return true;
}

function validateHeaderIntegrity(headers) {
  const required = ["x-request-id", "x-timestamp"];

  for (const header of required) {
    if (!headers.get(header)) {
      throw new Error(`Missing required header: ${header}`);
    }
  }

  return true;
}

function validateTimestamp(timestamp) {
  try {
    // Validate timestamp format (ISO 8601)
    if (
      typeof timestamp !== "string" ||
      !timestamp.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)
    ) {
      throw new Error("Invalid timestamp format (expected ISO 8601)");
    }

    const requestTime = new Date(timestamp).getTime();

    // Check if date is valid
    if (isNaN(requestTime)) {
      throw new Error("Invalid timestamp format");
    }

    const now = Date.now();

    // Must be within 5 minutes
    if (Math.abs(now - requestTime) > 300000) {
      throw new Error("Request timestamp outside acceptable window");
    }

    // Must not be in the future (by more than 1 second for clock skew)
    if (requestTime > now + 1000) {
      throw new Error("Request timestamp is in the future");
    }

    return true;
  } catch (error) {
    throw new Error(`Invalid timestamp: ${error.message}`);
  }
}

// Rate limiting: fixed 60s window, keyed by API key hash, per
// docs/04_CODE_STANDARDS.md ("rate_limit:{userId}:{endpoint}").
// Requires a KV binding (env.KV) — a Worker without one (e.g. local dev,
// unit tests, or a deployment that hasn't set up KV yet) degrades to
// "allow", matching the fail-soft pattern used across this codebase.
const DEFAULT_RATE_LIMIT_PER_MINUTE = 100;

async function checkRateLimit(apiKeyHash, env, endpoint = "cli") {
  if (!env || !env.KV || !apiKeyHash) {
    return true;
  }

  const limit = Number(env.RATE_LIMIT_PER_MINUTE) || DEFAULT_RATE_LIMIT_PER_MINUTE;
  const windowSeconds = 60;
  const windowId = Math.floor(Date.now() / 1000 / windowSeconds);
  const key = `rate_limit:${apiKeyHash}:${endpoint}:${windowId}`;

  const current = parseInt((await env.KV.get(key)) || "0", 10);
  if (current >= limit) {
    throw new Error(`Rate limit exceeded (${limit}/min)`);
  }

  await env.KV.put(key, String(current + 1), { expirationTtl: windowSeconds * 2 });

  return true;
}

// Data tier enforcement
function getDataTier(command) {
  // Map commands to data tiers
  const tierMap = {
    ping: "TIER_3", // System status - public
    "gh-open": "TIER_3", // Public URL generation
    ai: "TIER_2", // User prompts - sensitive
    gh: "TIER_2", // Code operations - sensitive
    sys: "TIER_3", // System info - public
  };

  return tierMap[command] || "TIER_2"; // Default to sensitive
}

function validateDataTier(tier) {
  if (!DATA_TIERS[tier]) {
    throw new Error(`Invalid data tier: ${tier}`);
  }

  return true;
}

// Request deduplication (replay attack prevention).
// Same fail-soft rule as checkRateLimit: without a KV binding there's
// nowhere to remember request IDs across invocations, so we allow the
// request rather than block on missing infrastructure.
async function checkRequestDeduplication(requestId, env) {
  if (!env || !env.KV || !requestId) {
    return true;
  }

  const key = `request_id:${requestId}`;
  const seen = await env.KV.get(key);
  if (seen) {
    throw new Error("Duplicate request ID (replay attack detected)");
  }

  // TTL matches the 5-minute timestamp acceptance window in
  // validateTimestamp() — no point remembering an ID longer than a
  // replay of it could possibly be accepted.
  await env.KV.put(key, "1", { expirationTtl: 300 });

  return true;
}

// Comprehensive security check
async function performSecurityCheck(request, headers, env) {
  // Validate structure
  validateRequestStructure(request);

  // Validate headers
  validateHeaderIntegrity(headers);

  // Validate timestamp
  const timestamp = headers.get("x-timestamp");
  validateTimestamp(timestamp);

  // Check rate limits
  const apiKeyHash = headers.get("x-api-key-hash");
  await checkRateLimit(apiKeyHash, env);

  // Check for replay attacks
  const requestId = headers.get("x-request-id");
  await checkRequestDeduplication(requestId, env);

  return {
    valid: true,
    tier: getDataTier(request.command),
    requestId,
    timestamp,
  };
}

export {
  DATA_TIERS,
  validateRequestStructure,
  validateHeaderIntegrity,
  validateTimestamp,
  checkRateLimit,
  getDataTier,
  validateDataTier,
  checkRequestDeduplication,
  performSecurityCheck,
};
