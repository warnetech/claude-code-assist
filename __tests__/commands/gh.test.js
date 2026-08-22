import handleGh from "../../worker/commands/gh.js";

describe("gh command", () => {
  describe("gh open", () => {
    it("opens claude with default repo", async () => {
      const result = await handleGh(["open"], {});
      expect(result.action).toBe("open_claude");
      expect(result.url).toContain("https://claude.ai/new?repo=");
      expect(result.url).toContain("claude-command-cli");
    });

    it("opens claude with specified repo", async () => {
      const result = await handleGh(["open", "my-repo"], {});
      expect(result.action).toBe("open_claude");
      expect(result.url).toContain("my-repo");
      expect(result.url).toContain("tewartech-node");
    });

    it("constructs correct github URL", async () => {
      const result = await handleGh(["open", "test-project"], {});
      expect(result.url).toBe(
        "https://claude.ai/new?repo=https://github.com/tewartech-node/test-project",
      );
    });
  });

  describe("gh push", () => {
    it("returns push instructions with default message", async () => {
      const result = await handleGh(["push"], {});
      expect(result.action).toBe("push_instructions");
      expect(result.instructions).toContain("git add .");
      expect(result.instructions.some((i) => i.includes("update"))).toBe(true);
    });

    it("returns push instructions with custom message", async () => {
      const result = await handleGh(["push", "feat: new feature"], {});
      expect(result.action).toBe("push_instructions");
      expect(
        result.instructions.some((i) => i.includes("feat: new feature")),
      ).toBe(true);
    });

    it("includes all required git commands", async () => {
      const result = await handleGh(["push", "test commit"], {});
      expect(result.instructions).toContain("git add .");
      expect(result.instructions.some((i) => i.includes("git commit"))).toBe(
        true,
      );
      expect(result.instructions.some((i) => i.includes("git push"))).toBe(
        true,
      );
    });
  });

  describe("gh pull", () => {
    it("returns pull instructions", async () => {
      const result = await handleGh(["pull"], {});
      expect(result.action).toBe("pull_instructions");
      expect(result.instructions).toContain("git pull");
    });
  });

  describe("error handling", () => {
    it("throws error when no subcommand provided", async () => {
      try {
        await handleGh([], {});
        expect(true).toBe(false);
      } catch (error) {
        expect(error.message).toContain("requires a subcommand");
      }
    });

    it("throws error for unknown subcommand", async () => {
      try {
        await handleGh(["unknown"], {});
        expect(true).toBe(false);
      } catch (error) {
        expect(error.message).toContain("Unknown gh subcommand");
      }
    });
  });
});
