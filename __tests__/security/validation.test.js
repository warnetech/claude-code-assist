import {
  validateRequestStructure,
  validateHeaderIntegrity,
  validateTimestamp,
  getDataTier,
  validateDataTier,
  DATA_TIERS,
} from "../../worker/utils/security.js";

describe("Request Validation & Security", () => {
  describe("request structure validation", () => {
    it("accepts valid requests with command", () => {
      const request = {
        command: "ping",
        args: [],
      };

      expect(() => validateRequestStructure(request)).not.toThrow();
    });

    it("accepts valid encrypted requests", () => {
      const request = {
        encrypted_data: "base64_encoded_data",
        signature: "hmac_signature",
      };

      expect(() => validateRequestStructure(request)).not.toThrow();
    });

    it("rejects requests without command or encrypted_data", () => {
      const request = {};

      expect(() => validateRequestStructure(request)).toThrow(
        "Missing command",
      );
    });

    it("rejects encrypted requests without signature", () => {
      const request = {
        encrypted_data: "base64_encoded_data",
      };

      expect(() => validateRequestStructure(request)).toThrow("signature");
    });

    it("rejects non-object requests", () => {
      expect(() => validateRequestStructure(null)).toThrow(
        "Invalid request structure",
      );
      expect(() => validateRequestStructure("string")).toThrow(
        "Invalid request structure",
      );
      expect(() => validateRequestStructure([])).toThrow(
        "Invalid request structure",
      );
    });
  });

  describe("header validation", () => {
    it("accepts requests with required headers", () => {
      const headers = new Map([
        ["x-request-id", "req-123"],
        ["x-timestamp", new Date().toISOString()],
      ]);

      expect(() => validateHeaderIntegrity(headers)).not.toThrow();
    });

    it("rejects requests missing x-request-id", () => {
      const headers = new Map([["x-timestamp", new Date().toISOString()]]);

      expect(() => validateHeaderIntegrity(headers)).toThrow("x-request-id");
    });

    it("rejects requests missing x-timestamp", () => {
      const headers = new Map([["x-request-id", "req-123"]]);

      expect(() => validateHeaderIntegrity(headers)).toThrow("x-timestamp");
    });
  });

  describe("timestamp validation", () => {
    it("accepts current timestamps", () => {
      const now = new Date().toISOString();
      expect(() => validateTimestamp(now)).not.toThrow();
    });

    it("accepts timestamps within 5 minute window", () => {
      const past = new Date(Date.now() - 240000).toISOString(); // 4 minutes ago
      expect(() => validateTimestamp(past)).not.toThrow();
    });

    it("rejects timestamps older than 5 minutes", () => {
      const old = new Date(Date.now() - 360000).toISOString(); // 6 minutes ago
      expect(() => validateTimestamp(old)).toThrow("outside acceptable window");
    });

    it("rejects future timestamps", () => {
      const future = new Date(Date.now() + 2000).toISOString(); // 2 seconds in future
      expect(() => validateTimestamp(future)).toThrow("future");
    });

    it("rejects invalid timestamp format", () => {
      expect(() => validateTimestamp("not-a-date")).toThrow(
        "Invalid timestamp",
      );
      expect(() => validateTimestamp("2026-13-45T25:61:61Z")).toThrow();
    });
  });

  describe("data tier assignment", () => {
    it("assigns TIER_3 to ping command", () => {
      expect(getDataTier("ping")).toBe("TIER_3");
    });

    it("assigns TIER_2 to ai command", () => {
      expect(getDataTier("ai")).toBe("TIER_2");
    });

    it("assigns TIER_2 to gh command", () => {
      expect(getDataTier("gh")).toBe("TIER_2");
    });

    it("assigns TIER_2 to unknown commands by default", () => {
      expect(getDataTier("unknown")).toBe("TIER_2");
    });
  });

  describe("data tier validation", () => {
    it("accepts valid TIER_1", () => {
      expect(() => validateDataTier("TIER_1")).not.toThrow();
    });

    it("accepts valid TIER_2", () => {
      expect(() => validateDataTier("TIER_2")).not.toThrow();
    });

    it("accepts valid TIER_3", () => {
      expect(() => validateDataTier("TIER_3")).not.toThrow();
    });

    it("rejects invalid tiers", () => {
      expect(() => validateDataTier("TIER_4")).toThrow("Invalid data tier");
      expect(() => validateDataTier("INVALID")).toThrow("Invalid data tier");
    });
  });

  describe("data tier information", () => {
    it("provides tier metadata", () => {
      expect(DATA_TIERS.TIER_1.name).toBe("Highly Sensitive");
      expect(DATA_TIERS.TIER_1.encrypted_at_rest).toBe(true);
    });

    it("includes all required tiers", () => {
      expect(DATA_TIERS.TIER_1).toBeDefined();
      expect(DATA_TIERS.TIER_2).toBeDefined();
      expect(DATA_TIERS.TIER_3).toBeDefined();
    });
  });
});
