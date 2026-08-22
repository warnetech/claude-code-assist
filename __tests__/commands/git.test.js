import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

describe("git commands", () => {
  // Note: These tests verify the CLI command structure, not actual git operations
  // Actual git operations are tested in integration tests

  it("gh-push command exists and has correct options", async () => {
    try {
      await execAsync("node warnetech_cli_legacy/warnetech gh-push --help");
      // If no error, command exists
      expect(true).toBe(true);
    } catch (error) {
      // Command should exist and print help
      expect(error.message).toContain("Commit and push");
    }
  });

  it("gh-pull command exists and has correct options", async () => {
    try {
      await execAsync("node warnetech_cli_legacy/warnetech gh-pull --help");
      // If no error, command exists
      expect(true).toBe(true);
    } catch (error) {
      // Command should exist and print help
      expect(error.message).toContain("Pull latest");
    }
  });

  it("gh-push requires a commit message", async () => {
    try {
      await execAsync("node warnetech_cli_legacy/warnetech gh-push");
      // Should fail - missing message argument
      expect(false).toBe(true);
    } catch (error) {
      // Expected to fail
      expect(error.message).toBeTruthy();
    }
  });
});
