import handlePing from "../../worker/commands/ping.js";

describe("ping command", () => {
  it("returns pong message", async () => {
    const result = await handlePing([], {});
    expect(result.message).toBe("pong");
  });

  it("includes timestamp", async () => {
    const result = await handlePing([], {});
    expect(result.timestamp).toBeDefined();
    expect(new Date(result.timestamp)).toBeInstanceOf(Date);
  });
});
