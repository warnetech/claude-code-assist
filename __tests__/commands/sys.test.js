import handleSys from "../../worker/commands/sys.js";

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
  };
}

describe("sys command", () => {
  it("throws when no action is given", async () => {
    await expect(handleSys([], {})).rejects.toThrow("System action required");
  });

  it("throws for an unknown action", async () => {
    await expect(handleSys(["bogus"], {})).rejects.toThrow("Unknown action");
  });

  describe("status", () => {
    it("reports kv/nvidia as not_configured without bindings", async () => {
      const result = await handleSys(["status"], {});
      expect(result.status).toBe("healthy");
      expect(result.services.kv).toBe("not_configured");
      expect(result.services.nvidia_api).toBe("not_configured");
    });

    it("reports services as ok when configured", async () => {
      const result = await handleSys(["status"], {
        KV: makeFakeKV(),
        NVIDIA_API_KEY: "key",
      });
      expect(result.services.kv).toBe("ok");
      expect(result.services.nvidia_api).toBe("ok");
    });
  });

  describe("quota", () => {
    it("returns labeled example data without a KV binding", async () => {
      const result = await handleSys(["quota", "check"], {});
      expect(result.live).toBe(false);
      expect(result.note).toMatch(/example data/);
      expect(result.api_calls).toEqual({ used: 45, limit: 100 });
    });

    it("tracks live usage with a KV binding", async () => {
      const env = { KV: makeFakeKV() };
      const first = await handleSys(["quota", "check"], env);
      const second = await handleSys(["quota", "check"], env);
      expect(first.live).toBe(true);
      expect(first.api_calls.used).toBe(1);
      expect(second.api_calls.used).toBe(2);
    });

    it("throws for an unknown quota action", async () => {
      await expect(handleSys(["quota", "bogus"], {})).rejects.toThrow(
        "Unknown quota action",
      );
    });
  });

  describe("sync", () => {
    it("is honest about not being configured rather than faking success", async () => {
      const result = await handleSys(["sync"], {});
      expect(result.synced).toBe(false);
      expect(result.reason).toBe("WARNETECH_SERVER_URL not configured");
    });

    it("forwards to WARNETECH_SERVER_URL when configured", async () => {
      const originalFetch = globalThis.fetch;
      globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({ baselines_updated: 3, signatures_updated: 5 }),
      });
      try {
        const result = await handleSys(["sync"], {
          WARNETECH_SERVER_URL: "https://server.example",
        });
        expect(result.synced).toBe(true);
        expect(result.baselines_updated).toBe(3);
        expect(result.signatures_updated).toBe(5);
      } finally {
        globalThis.fetch = originalFetch;
      }
    });
  });

  describe("detect-anomalies", () => {
    it("reports source: not_configured without a server URL", async () => {
      const result = await handleSys(["detect-anomalies"], {});
      expect(result.anomalies_detected).toBe(0);
      expect(result.source).toBe("not_configured");
    });
  });

  describe("rollup", () => {
    it("reports it needs a KV binding when none is present", async () => {
      const result = await handleSys(["rollup"], {});
      expect(result.rollup_completed).toBe(false);
      expect(result.records_aggregated).toBe(0);
    });

    it("aggregates tracked quota keys with a KV binding", async () => {
      const env = { KV: makeFakeKV() };
      await handleSys(["quota", "check"], env);
      const result = await handleSys(["rollup"], env);
      expect(result.rollup_completed).toBe(true);
      expect(result.records_aggregated).toBe(1);
    });
  });
});
