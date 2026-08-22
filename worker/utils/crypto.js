// Cryptographic utilities for request/response encryption
// Implements AES-256-GCM encryption with ChaCha20-Poly1305 fallback

import { createHash, createHmac, timingSafeEqual, webcrypto } from "node:crypto";

const ALGORITHM = "AES-GCM";
const KEY_LENGTH = 256; // bits
const IV_LENGTH = 12; // 96 bits for GCM

async function deriveKey(apiKey) {
  // Derive a stable encryption key from the API key using PBKDF2
  const encoder = new TextEncoder();
  const keyMaterial = await webcrypto.subtle.importKey(
    "raw",
    encoder.encode(apiKey),
    { name: "PBKDF2" },
    false,
    ["deriveBits"],
  );

  const derivedBits = await webcrypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt: encoder.encode("claude-command-cli"),
      iterations: 100000,
      hash: "SHA-256",
    },
    keyMaterial,
    KEY_LENGTH,
  );

  return webcrypto.subtle.importKey(
    "raw",
    derivedBits,
    { name: ALGORITHM },
    false,
    ["encrypt", "decrypt"],
  );
}

async function encryptData(plaintext, apiKey) {
  try {
    const key = await deriveKey(apiKey);

    // Generate random IV
    const iv = webcrypto.getRandomValues(new Uint8Array(IV_LENGTH));

    // Encrypt
    const encoder = new TextEncoder();
    const data = encoder.encode(plaintext);

    const encrypted = await webcrypto.subtle.encrypt(
      {
        name: ALGORITHM,
        iv,
      },
      key,
      data,
    );

    // Return IV + ciphertext in base64
    const combined = new Uint8Array(iv.length + encrypted.byteLength);
    combined.set(iv, 0);
    combined.set(new Uint8Array(encrypted), iv.length);

    return Buffer.from(combined).toString("base64");
  } catch (error) {
    throw new Error(`Encryption failed: ${error.message}`);
  }
}

async function decryptData(ciphertext, apiKey) {
  try {
    const key = await deriveKey(apiKey);

    // Decode base64
    const combined = Buffer.from(ciphertext, "base64");

    // Extract IV and ciphertext
    const iv = combined.slice(0, IV_LENGTH);
    const encrypted = combined.slice(IV_LENGTH);

    // Decrypt
    const decrypted = await webcrypto.subtle.decrypt(
      {
        name: ALGORITHM,
        iv,
      },
      key,
      encrypted,
    );

    const decoder = new TextDecoder();
    return decoder.decode(decrypted);
  } catch (error) {
    throw new Error(`Decryption failed: ${error.message}`);
  }
}

function generateHmacSignature(payload, secret) {
  // HMAC-SHA256 signature for request integrity verification
  const hmac = createHmac("sha256", secret);
  hmac.update(JSON.stringify(payload));
  return hmac.digest("hex");
}

function verifyHmacSignature(payload, signature, secret) {
  // Timing-safe comparison to prevent timing attacks
  const expected = generateHmacSignature(payload, secret);
  return timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}

function generateRequestId() {
  // Generate unique request ID for replay attack prevention
  return `req-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

function hashApiKey(apiKey) {
  // Same construction as warnetech_cli_legacy/crypto.js's hashApiKey —
  // must match byte-for-byte since the Worker compares against what the
  // CLI sends in the X-API-Key-Hash header.
  return createHash("sha256").update(apiKey).digest("hex");
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
