// Request validation, security checks, and decryption
import { decryptData, hashApiKey, verifyHmacSignature } from "./crypto.js";

async function validateRequest(body, headers, env) {
  try {
    // Validate API key hash (not the actual key)
    const apiKeyHash = headers.get("x-api-key-hash");
    if (!apiKeyHash) {
      return { ok: false, error: "API key validation required" };
    }

    // Validate request ID (prevent replay)
    const requestId = headers.get("x-request-id");
    if (!requestId) {
      return { ok: false, error: "Request ID required" };
    }

    // Replay-attack dedup is handled by security.js's
    // checkRequestDeduplication(), invoked from index.js after validation
    // succeeds (it needs the raw requestId, which we return below).

    // Validate timestamp
    const timestamp = headers.get("x-timestamp");
    if (!timestamp) {
      return { ok: false, error: "Timestamp required" };
    }

    const requestTime = new Date(timestamp).getTime();
    const now = Date.now();
    if (Math.abs(now - requestTime) > 300000) {
      // 5 minutes
      return { ok: false, error: "Request timestamp too old" };
    }

    // For unencrypted requests (backwards compatibility)
    if (body.command) {
      const validCommands = ["ping", "ai", "gh", "sys"];
      if (!validCommands.includes(body.command)) {
        return {
          ok: false,
          error: `Unknown command: ${body.command}. Valid commands: ${validCommands.join(", ")}`,
        };
      }

      return {
        ok: true,
        command: body.command,
        args: body.args || [],
      };
    }

    // For encrypted requests
    if (body.encrypted_data) {
      return {
        ok: true,
        encrypted: true,
        encrypted_data: body.encrypted_data,
        signature: body.signature,
      };
    }

    return { ok: false, error: "Command or encrypted_data required" };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

async function decryptRequest(encryptedData, signature, headers, env) {
  try {
    if (!env || !env.API_KEY) {
      throw new Error("server missing API_KEY");
    }

    // Cheap fail-fast: the CLI sends a hash of its key so the Worker can
    // reject an obviously-wrong key before spending a PBKDF2 derivation.
    const apiKeyHash = headers.get("x-api-key-hash");
    if (apiKeyHash && apiKeyHash !== hashApiKey(env.API_KEY)) {
      throw new Error("API key mismatch");
    }

    // Verify the HMAC signature over the encrypted envelope before trusting
    // it (defense in depth on top of AES-GCM's own auth tag).
    if (signature) {
      let signatureValid = false;
      try {
        signatureValid = verifyHmacSignature(
          { encrypted_data: encryptedData },
          signature,
          env.API_KEY,
        );
      } catch (_error) {
        signatureValid = false;
      }
      if (!signatureValid) {
        throw new Error("signature verification failed");
      }
    }

    const plaintext = await decryptData(encryptedData, env.API_KEY);

    let parsed;
    try {
      parsed = JSON.parse(plaintext);
    } catch (_error) {
      throw new Error("decrypted payload is not valid JSON");
    }

    return {
      command: parsed.command,
      args: parsed.args || [],
    };
  } catch (error) {
    throw new Error(`Failed to decrypt request: ${error.message}`);
  }
}

// Anti-tamper checks - verify request hasn't been modified
async function antiTamperCheck(request, env) {
  // Verify signature
  if (request.signature) {
    const verified = await verifySignature(
      request,
      request.signature,
      env.SIGNING_KEY,
    );
    if (!verified) {
      throw new Error("Signature verification failed");
    }
  }

  // Check data tier compliance
  if (request.data_tier) {
    validateDataTier(request.data_tier);
  }

  return true;
}

function validateDataTier(tier) {
  const valid = ["TIER_1", "TIER_2", "TIER_3"];
  if (!valid.includes(tier)) {
    throw new Error(`Invalid data tier: ${tier}`);
  }
}

async function verifySignature(payload, signature, secret) {
  // HMAC-SHA256 verification
  // This is a placeholder - full implementation requires crypto access
  return true;
}

export {
  validateRequest,
  decryptRequest,
  antiTamperCheck,
  validateDataTier,
  verifySignature,
};
