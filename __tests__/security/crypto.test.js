import {
  encryptData,
  decryptData,
  generateHmacSignature,
  verifyHmacSignature,
  generateRequestId,
  hashApiKey,
} from "../../warnetech_cli_legacy/crypto.js";

describe("Cryptography", () => {
  const testApiKey = "test-api-key-12345";
  const plaintext = '{"command":"ping","args":[]}';

  describe("encryption/decryption", () => {
    it("encrypts and decrypts data correctly", async () => {
      const encrypted = await encryptData(plaintext, testApiKey);
      expect(encrypted).toBeTruthy();
      expect(typeof encrypted).toBe("string");

      const decrypted = await decryptData(encrypted, testApiKey);
      expect(decrypted).toBe(plaintext);
    });

    it("produces different ciphertext for same plaintext (IV randomization)", async () => {
      const encrypted1 = await encryptData(plaintext, testApiKey);
      const encrypted2 = await encryptData(plaintext, testApiKey);

      expect(encrypted1).not.toBe(encrypted2);
    });

    it("fails decryption with wrong API key", async () => {
      const encrypted = await encryptData(plaintext, testApiKey);
      const wrongKey = "wrong-key-12345";

      try {
        await decryptData(encrypted, wrongKey);
        expect(false).toBe(true); // Should not reach here
      } catch (error) {
        expect(error.message).toContain("Decryption failed");
      }
    });

    it("fails decryption with corrupted ciphertext", async () => {
      const encrypted = await encryptData(plaintext, testApiKey);
      const corrupted = encrypted.slice(0, -10) + "corrupted";

      try {
        await decryptData(corrupted, testApiKey);
        expect(false).toBe(true); // Should not reach here
      } catch (error) {
        expect(error.message).toContain("Decryption failed");
      }
    });
  });

  describe("HMAC signatures", () => {
    it("generates consistent signatures", () => {
      const payload = { command: "ping" };
      const sig1 = generateHmacSignature(payload, testApiKey);
      const sig2 = generateHmacSignature(payload, testApiKey);

      expect(sig1).toBe(sig2);
    });

    it("generates different signatures for different payloads", () => {
      const payload1 = { command: "ping" };
      const payload2 = { command: "ai" };

      const sig1 = generateHmacSignature(payload1, testApiKey);
      const sig2 = generateHmacSignature(payload2, testApiKey);

      expect(sig1).not.toBe(sig2);
    });

    it("verifies valid signatures", () => {
      const payload = { command: "ping", args: [] };
      const signature = generateHmacSignature(payload, testApiKey);

      expect(() =>
        verifyHmacSignature(payload, signature, testApiKey),
      ).not.toThrow();
    });

    it("rejects invalid signatures", () => {
      const payload = { command: "ping" };
      const wrongSig = "invalid_signature";

      expect(() =>
        verifyHmacSignature(payload, wrongSig, testApiKey),
      ).toThrow();
    });
  });

  describe("request ID generation", () => {
    it("generates unique request IDs", () => {
      const id1 = generateRequestId();
      const id2 = generateRequestId();

      expect(id1).not.toBe(id2);
      expect(id1.startsWith("req-")).toBe(true);
      expect(id2.startsWith("req-")).toBe(true);
    });
  });

  describe("API key hashing", () => {
    it("produces consistent hashes", () => {
      const hash1 = hashApiKey(testApiKey);
      const hash2 = hashApiKey(testApiKey);

      expect(hash1).toBe(hash2);
    });

    it("produces different hashes for different keys", () => {
      const hash1 = hashApiKey("key1");
      const hash2 = hashApiKey("key2");

      expect(hash1).not.toBe(hash2);
    });

    it("produces hex string hashes", () => {
      const hash = hashApiKey(testApiKey);
      expect(/^[a-f0-9]+$/.test(hash)).toBe(true);
    });
  });
});
