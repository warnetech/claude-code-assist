import {
  checkRateLimit,
  checkRequestDeduplication,
} from "../../worker/utils/security.js";

function makeFakeKV() {
  const store = new Map();
  return {
    async get(key) {
      return store.has(key) ? store.get(key) : null;
    },
    async put(key, value) {
      store.set(key, value);
    },
  };
}

describe("checkRateLimit", () => {
  it("allows requests when no KV binding is present (fail-open)", async () => {
    await expect(checkRateLimit("hash123", {})).resolves.toBe(true);
    await expect(checkRateLimit("hash123", undefined)).resolves.toBe(true);
  });

  it("allows requests up to the configured limit, then throws", async () => {
    const env = { KV: makeFakeKV(), RATE_LIMIT_PER_MINUTE: "3" };
    await expect(checkRateLimit("hash123", env)).resolves.toBe(true);
    await expect(checkRateLimit("hash123", env)).resolves.toBe(true);
    await expect(checkRateLimit("hash123", env)).resolves.toBe(true);
    await expect(checkRateLimit("hash123", env)).rejects.toThrow(
      /Rate limit exceeded/,
    );
  });

  it("tracks separate keys independently", async () => {
    const env = { KV: makeFakeKV(), RATE_LIMIT_PER_MINUTE: "1" };
    await expect(checkRateLimit("hash-a", env)).resolves.toBe(true);
    await expect(checkRateLimit("hash-b", env)).resolves.toBe(true);
    await expect(checkRateLimit("hash-a", env)).rejects.toThrow();
    await expect(checkRateLimit("hash-b", env)).rejects.toThrow();
  });
});

describe("checkRequestDeduplication", () => {
  it("allows requests when no KV binding is present (fail-open)", async () => {
    await expect(checkRequestDeduplication("req-1", {})).resolves.toBe(true);
  });

  it("allows a request ID the first time and rejects a replay", async () => {
    const env = { KV: makeFakeKV() };
    await expect(checkRequestDeduplication("req-1", env)).resolves.toBe(true);
    await expect(checkRequestDeduplication("req-1", env)).rejects.toThrow(
      /Duplicate request ID/,
    );
  });

  it("treats different request IDs independently", async () => {
    const env = { KV: makeFakeKV() };
    await expect(checkRequestDeduplication("req-a", env)).resolves.toBe(true);
    await expect(checkRequestDeduplication("req-b", env)).resolves.toBe(true);
  });
});
