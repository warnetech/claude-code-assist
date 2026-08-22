// CLI-side cryptographic utilities for request/response handling
import crypto from "crypto";

const ALGORITHM = "aes-256-gcm";
// Canonical wire format, shared with worker/utils/crypto.js:
//   iv(12) || ciphertext+tag
// 96-bit IV is the NIST SP 800-38D recommendation for GCM, and WebCrypto
// appends the auth tag to the ciphertext rather than exposing it separately.
const IV_LENGTH = 12;
const AUTH_TAG_LENGTH = 16;

function deriveKey(apiKey) {
  // Derive encryption key from API key using PBKDF2
  return crypto.pbkdf2Sync(
    apiKey,
    "claude-command-cli",
    100000,
    32, // 256 bits
    "sha256",
  );
}

function encryptData(plaintext, apiKey) {
  try {
    const key = deriveKey(apiKey);
    const iv = crypto.randomBytes(IV_LENGTH);

    const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
    let encrypted = cipher.update(plaintext, "utf8", "hex");
    encrypted += cipher.final("hex");

    const authTag = cipher.getAuthTag();

    // Return IV + ciphertext + authTag in base64 (tag last, matching WebCrypto)
    const combined = Buffer.concat([
      iv,
      Buffer.from(encrypted, "hex"),
      authTag,
    ]);
    return combined.toString("base64");
  } catch (error) {
    throw new Error(`Encryption failed: ${error.message}`);
  }
}

function decryptData(ciphertext, apiKey) {
  try {
    const key = deriveKey(apiKey);
    const combined = Buffer.from(ciphertext, "base64");

    if (combined.length <= IV_LENGTH + AUTH_TAG_LENGTH) {
      throw new Error("packet too short");
    }

    // Extract IV, encrypted data, and trailing authTag
    const iv = combined.slice(0, IV_LENGTH);
    const encrypted = combined.slice(
      IV_LENGTH,
      combined.length - AUTH_TAG_LENGTH,
    );
    const authTag = combined.slice(combined.length - AUTH_TAG_LENGTH);

    const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
    decipher.setAuthTag(authTag);

    let decrypted = decipher.update(encrypted);
    decrypted = Buffer.concat([decrypted, decipher.final()]);

    return decrypted.toString("utf8");
  } catch (error) {
    throw new Error(`Decryption failed: ${error.message}`);
  }
}

function generateHmacSignature(payload, secret) {
  const hmac = crypto.createHmac("sha256", secret);
  hmac.update(JSON.stringify(payload));
  return hmac.digest("hex");
}

function verifyHmacSignature(payload, signature, secret) {
  const expected = generateHmacSignature(payload, secret);
  // Timing-safe comparison
  return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}

function generateRequestId() {
  return `req-${Date.now()}-${crypto.randomBytes(4).toString("hex")}`;
}

function hashApiKey(apiKey) {
  // Hash API key for storage/comparison
  return crypto.createHash("sha256").update(apiKey).digest("hex");
}

export {
  encryptData,
  decryptData,
  deriveKey,
  generateHmacSignature,
  verifyHmacSignature,
  generateRequestId,
  hashApiKey,
};
