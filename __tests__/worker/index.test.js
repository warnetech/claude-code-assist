// End-to-end coverage of worker/index.js's /cli handler: this is the path
// that was completely broken before (decryptRequest() unconditionally
// threw "not yet implemented"), so these tests exercise the full
// CLI-shaped encrypted request rather than calling command handlers
// directly.
import * as legacyCrypto from "../../warnetech_cli_legacy/crypto.js";
import worker from "../../worker/index.js";

const API_KEY = "test-shared-secret";

function makeFakeKV() {
  const store = new Map();
  return {
    async get(key) {
      return store.has(key) ? store.get(key) : null;
    },
    async put(key, value) {
      store.set(key, value);
    },
    async list({ prefix }) {
      return {
        keys: [...store.keys()]
          .filter((k) => k.startsWith(prefix))
          .map((name) => ({ name })),
      };
    },
    _store: store,
  };
}

async function sendEncrypted(command, args, { env, headerOverrides, bodyOverrides } = {}) {
  const payload = JSON.stringify({ command, args });
  const encryptedPayload = legacyCrypto.encryptData(payload, API_KEY);
  const signature = legacyCrypto.generateHmacSignature(
    { encrypted_data: encryptedPayload },
    API_KEY,
  );

  const headers = new Headers({
    "Content-Type": "application/json",
    "X-API-Key-Hash": legacyCrypto.hashApiKey(API_KEY),
    "X-Request-ID": legacyCrypto.generateRequestId(),
    "X-Timestamp": new Date().toISOString(),
    ...headerOverrides,
  });

  const body = JSON.stringify({
    encrypted_data: encryptedPayload,
    signature,
    ...bodyOverrides,
  });

  const request = new Request("http://worker.local/cli", {
    method: "POST",
    headers,
    body,
  });

  const response = await worker.fetch(request, env || { API_KEY }, {});
  const data = await response.json();
  return { status: response.status, data };
}

describe("worker /cli end-to-end (encrypted requests)", () => {
  it("decrypts a ping request and returns pong", async () => {
    const { status, data } = await sendEncrypted("ping", []);
    expect(status).toBe(200);
    expect(data.ok).toBe(true);
    expect(data.data.message).toBe("pong");
  });

  it("decrypts a gh open request and returns both url and claude_url", async () => {
    const { data } = await sendEncrypted("gh", ["open", "my-repo"]);
    expect(data.data.url).toBe(data.data.claude_url);
    expect(data.data.url).toContain("my-repo");
    expect(data.data.repo_url).toBe(
      "https://github.com/tewartech-node/my-repo",
    );
  });

  it("rejects a request encrypted with the wrong API key", async () => {
    const { status, data } = await sendEncrypted("ping", [], {
      env: { API_KEY: "not-the-real-key" },
    });
    expect(status).toBe(400);
    expect(data.ok).toBe(false);
  });

  it("rejects a request with a tampered signature", async () => {
    const { status, data } = await sendEncrypted("ping", [], {
      bodyOverrides: { signature: "0".repeat(64) },
    });
    expect(status).toBe(400);
    expect(data.error).toMatch(/signature verification failed/);
  });

  it("rejects the request if the server has no API_KEY configured", async () => {
    const { status, data } = await sendEncrypted("ping", [], { env: {} });
    expect(status).toBe(400);
    expect(data.error).toMatch(/API_KEY/);
  });

  describe("with a KV binding", () => {
    it("enforces rate limiting per RATE_LIMIT_PER_MINUTE", async () => {
      const env = { API_KEY, KV: makeFakeKV(), RATE_LIMIT_PER_MINUTE: "2" };
      const r1 = await sendEncrypted("ping", [], { env });
      const r2 = await sendEncrypted("ping", [], { env });
      const r3 = await sendEncrypted("ping", [], { env });
      expect(r1.status).toBe(200);
      expect(r2.status).toBe(200);
      expect(r3.status).toBe(429);
    });

    it("rejects a replayed request ID", async () => {
      const env = { API_KEY, KV: makeFakeKV() };
      const requestId = legacyCrypto.generateRequestId();
      const headerOverrides = { "X-Request-ID": requestId };

      const r1 = await sendEncrypted("ping", [], { env, headerOverrides });
      const r2 = await sendEncrypted("ping", [], { env, headerOverrides });
      expect(r1.status).toBe(200);
      expect(r2.status).toBe(429);
    });

    it("tracks quota usage live across requests", async () => {
      const env = { API_KEY, KV: makeFakeKV() };
      const r1 = await sendEncrypted("sys", ["quota", "check"], { env });
      const r2 = await sendEncrypted("sys", ["quota", "check"], { env });
      expect(r1.data.data.live).toBe(true);
      expect(r1.data.data.api_calls.used).toBe(1);
      expect(r2.data.data.api_calls.used).toBe(2);
    });
  });

  describe("without a KV binding", () => {
    it("reports quota as example data rather than fabricating live numbers", async () => {
      const { data } = await sendEncrypted("sys", ["quota", "check"]);
      expect(data.data.live).toBe(false);
      expect(data.data.note).toMatch(/example data/);
    });

    it("reports sync as not-configured rather than fabricating a result", async () => {
      const { data } = await sendEncrypted("sys", ["sync"]);
      expect(data.data.synced).toBe(false);
      expect(data.data.reason).toBe("WARNETECH_SERVER_URL not configured");
    });
  });
});
