export async function ghOpen(args, env) {
  const repo = args || "claude-command-cli";
  const repoUrl = `https://github.com/tewartech-node/${repo}`;
  const url = `https://claude.ai/new?repo=${repoUrl}`;

  return {
    ok: true,
    action: "open_claude",
    // `url` stays the claude.ai wrapper link for backwards compatibility
    // with existing callers/tests; `claude_url` is the same value under
    // the name the CLI (warnetech_cli_legacy/warnetech) actually reads,
    // and `repo_url` exposes the plain GitHub link too.
    url,
    claude_url: url,
    repo_url: repoUrl,
  };
}

export async function ghPush(args, env) {
  const message = args || "update";

  return {
    ok: true,
    action: "push_instructions",
    instructions: [
      "Run the following in Termux:",
      "git add .",
      `git commit -m "${message}"`,
      "git push origin main",
    ],
  };
}

export async function ghPull(env) {
  return {
    ok: true,
    action: "pull_instructions",
    instructions: ["Run the following in Termux:", "git pull"],
  };
}

async function handleGh(args, env) {
  if (!args || args.length === 0) {
    throw new Error("gh command requires a subcommand: open, push, or pull");
  }

  const [subcommand, ...subargs] = Array.isArray(args) ? args : [args];

  switch (subcommand) {
    case "open":
      return ghOpen(subargs[0], env);

    case "push":
      return ghPush(subargs[0], env);

    case "pull":
      return ghPull(env);

    default:
      throw new Error(`Unknown gh subcommand: ${subcommand}`);
  }
}

export default handleGh;
