// Cross-implementation check: the legacy Node CLI and the Cloudflare Worker
// are the two ends of the same encrypted channel, so they must agree on the
// AES-GCM wire format.
//
// Canonical format: iv(12) || ciphertext+tag
// 96-bit IV per NIST SP 800-38D; the tag trails the ciphertext because
// WebCrypto does not expose it separately.
import * as legacy from "../../warnetech_cli_legacy/crypto.js";
import * as worker from "../../worker/utils/crypto.js";

const API_KEY = "test-password";
const PLAINTEXT = "warnetech-interop";

describe("Legacy CLI <-> Worker AES-GCM interop", () => {
  test("each side round-trips itself", async () => {
    expect(
      legacy.decryptData(legacy.encryptData(PLAINTEXT, API_KEY), API_KEY),
    ).toBe(PLAINTEXT);
    const w = await worker.encryptData(PLAINTEXT, API_KEY);
    expect(await worker.decryptData(w, API_KEY)).toBe(PLAINTEXT);
  });

  test("both sides derive the same 256-bit key", async () => {
    expect(legacy.deriveKey(API_KEY).length).toBe(32);
    await expect(worker.deriveKey(API_KEY)).resolves.toBeDefined();
  });

  test("legacy encrypt -> worker decrypt", async () => {
    const packet = legacy.encryptData(PLAINTEXT, API_KEY);
    expect(await worker.decryptData(packet, API_KEY)).toBe(PLAINTEXT);
  });

  test("worker encrypt -> legacy decrypt", async () => {
    const packet = await worker.encryptData(PLAINTEXT, API_KEY);
    expect(legacy.decryptData(packet, API_KEY)).toBe(PLAINTEXT);
  });

  test("both sides emit the same wire layout", async () => {
    const l = Buffer.from(legacy.encryptData(PLAINTEXT, API_KEY), "base64");
    const w = Buffer.from(
      await worker.encryptData(PLAINTEXT, API_KEY),
      "base64",
    );
    expect(l.length).toBe(w.length);
    // iv(12) + ciphertext(=plaintext length for GCM) + tag(16)
    expect(l.length).toBe(12 + PLAINTEXT.length + 16);
  });

  test("tampering with the trailing tag fails authentication", () => {
    const packet = Buffer.from(
      legacy.encryptData(PLAINTEXT, API_KEY),
      "base64",
    );
    packet[packet.length - 1] ^= 0x01;
    expect(() =>
      legacy.decryptData(packet.toString("base64"), API_KEY),
    ).toThrow(/Decryption failed/);
  });

  test("a truncated packet is rejected", () => {
    expect(() =>
      legacy.decryptData(Buffer.alloc(8).toString("base64"), API_KEY),
    ).toThrow(/Decryption failed/);
  });
});
