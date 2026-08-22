#!/usr/bin/env python3
"""Apply a patch, gate it on the test suites, and optionally publish it.

The gate is the point: if the tests fail, the patch is REVERTED. The naive
form of this tool leaves a failing patch sitting in the working tree, so the
next run stacks a second patch on top of broken code.

Safety rules, in order of importance:

1. Refuses to run on a dirty working tree. Rollback resets tracked files, so
   uncommitted work would be destroyed.
2. Validates the patch with `git apply --check` before touching anything, and
   rejects patches whose paths escape the repository.
3. Reverts the patch if either suite fails.
4. Never pushes unless asked. Publishing is opt-in via --push, goes to an
   explicit branch, and refuses main/master.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

RUNTIME = Path.home() / ".warnetech"
LOG_FILE = RUNTIME / "logs" / "autopatch.log"
PROTECTED_BRANCHES = {"main", "master"}


class AutopatchError(RuntimeError):
    """Raised when the pipeline refuses to proceed or a step fails."""


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as handle:
        handle.write(f"[{ts}] {msg}\n")


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, capturing output so failures are diagnosable."""
    log(f"RUN: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-5:]
        log(f"FAILED ({result.returncode}): {' | '.join(tail)}")
        if check:
            raise AutopatchError(f"{' '.join(cmd)} failed: {' | '.join(tail)}")
    return result


# -- repository state -------------------------------------------------------


def current_branch(repo: Path) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()


def head_commit(repo: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()


def is_dirty(repo: Path) -> bool:
    """True if TRACKED files have uncommitted changes.

    Untracked files are ignored: rollback only touches tracked files plus the
    specific paths the patch added, so stray files are never at risk.
    """
    result = run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo
    )
    return bool(result.stdout.strip())


def require_clean_tree(repo: Path) -> None:
    if is_dirty(repo):
        raise AutopatchError(
            "working tree is dirty; commit or stash first. Rollback resets "
            "tracked files and would discard uncommitted work."
        )


# -- patch handling ---------------------------------------------------------


def patch_paths(repo: Path, patch: Path) -> list[str]:
    """Files the patch touches, per git's own parse.

    `--numstat -z` emits one NUL-terminated record per file, each of the
    form "<added>\\t<deleted>\\t<path>".
    """
    result = run(["git", "apply", "--numstat", "-z", str(patch)], cwd=repo)
    paths = []
    for record in result.stdout.split("\0"):
        if not record.strip():
            continue
        parts = record.split("\t")
        if len(parts) >= 3:
            paths.append(parts[2])
    return paths


def validate_patch(repo: Path, patch: Path) -> list[str]:
    """Check the patch applies cleanly and stays inside the repository."""
    if not patch.exists():
        raise AutopatchError(f"patch not found: {patch}")

    paths = patch_paths(repo, patch)
    if not paths:
        raise AutopatchError("patch touches no files")

    for path in paths:
        resolved = (repo / path).resolve()
        if not str(resolved).startswith(str(repo.resolve())):
            raise AutopatchError(f"patch escapes the repository: {path}")

    run(["git", "apply", "--check", str(patch)], cwd=repo)
    log(f"Patch validated: {len(paths)} file(s)")
    return paths


def apply_patch(repo: Path, patch: Path) -> None:
    log(f"Applying patch: {patch}")
    run(["git", "apply", str(patch)], cwd=repo)


def revert_patch(repo: Path, checkpoint: str, added: list[str]) -> None:
    """Return the tree to the recorded commit, discarding the patch.

    `git reset --hard` restores tracked files; files the patch CREATED are
    untracked and survive it, so they are removed individually. A blanket
    `git clean -fd` would also delete unrelated untracked files, which is
    not this tool's to destroy.
    """
    log(f"Reverting to {checkpoint[:8]}")
    run(["git", "reset", "--hard", checkpoint], cwd=repo)
    for path in added:
        target = repo / path
        if target.is_file():
            target.unlink()
            log(f"Removed patch-created file: {path}")


# -- tests ------------------------------------------------------------------


def run_tests(repo: Path) -> dict:
    """Run both suites. Returns per-suite results; never raises on failure."""
    log("Running Python tests")
    py = run([sys.executable, "-m", "pytest", "-q"], cwd=repo, check=False)
    log("Running JS tests")
    js = run(["npm", "test"], cwd=repo, check=False)
    return {
        "python_ok": py.returncode == 0,
        "js_ok": js.returncode == 0,
        "all_ok": py.returncode == 0 and js.returncode == 0,
    }


# -- publish ----------------------------------------------------------------


def commit(repo: Path, message: str, paths: list[str]) -> str:
    # Stage only what the patch touched, so unrelated files are never swept in.
    run(["git", "add", "--"] + paths, cwd=repo)
    run(["git", "commit", "-m", message], cwd=repo)
    return head_commit(repo)


def push(repo: Path, branch: str) -> None:
    if branch in PROTECTED_BRANCHES:
        raise AutopatchError(f"refusing to push to protected branch: {branch}")
    run(["git", "push", "-u", "origin", branch], cwd=repo)


# -- pipeline ---------------------------------------------------------------


def autopatch(
    patch_path: str | Path,
    repo: Optional[Path] = None,
    message: Optional[str] = None,
    do_push: bool = False,
    dry_run: bool = False,
) -> dict:
    repo = Path(repo or Path.cwd()).resolve()
    patch = Path(patch_path).resolve()

    log(f"Starting autopatch: {patch}")
    require_clean_tree(repo)
    paths = validate_patch(repo, patch)

    if dry_run:
        log("Dry run: not applying")
        return {"dry_run": True, "files": paths, "applied": False}

    checkpoint = head_commit(repo)
    # Recorded before applying: these are the files rollback must delete,
    # since a reset alone leaves patch-created files behind as untracked.
    created = [p for p in paths if not (repo / p).exists()]
    apply_patch(repo, patch)

    results = run_tests(repo)
    if not results["all_ok"]:
        revert_patch(repo, checkpoint, created)
        log("Tests failed; patch reverted")
        return {"applied": False, "reverted": True, "tests": results, "files": paths}

    sha = commit(repo, message or f"fix: apply {patch.name}", paths)
    branch = current_branch(repo)

    pushed = False
    if do_push:
        push(repo, branch)
        pushed = True

    log(f"Autopatch complete: {sha[:8]} on {branch} (pushed={pushed})")
    return {
        "applied": True,
        "reverted": False,
        "tests": results,
        "files": paths,
        "commit": sha,
        "branch": branch,
        "pushed": pushed,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="warnetech-autopatch")
    parser.add_argument("patch", nargs="?", default="incoming.patch")
    parser.add_argument("--repo", default=None, help="repository root (default: cwd)")
    parser.add_argument("-m", "--message", default=None, help="commit message")
    parser.add_argument(
        "--push",
        action="store_true",
        help="publish to origin after tests pass (off by default)",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate only")
    args = parser.parse_args(argv)

    try:
        result = autopatch(
            args.patch,
            repo=Path(args.repo) if args.repo else None,
            message=args.message,
            do_push=args.push,
            dry_run=args.dry_run,
        )
    except AutopatchError as exc:
        print(f"autopatch: {exc}", file=sys.stderr)
        return 1

    if result.get("dry_run"):
        print(f"Patch is valid, touches {len(result['files'])} file(s).")
        return 0
    if not result["applied"]:
        print("Tests failed. Patch reverted; the tree is unchanged.", file=sys.stderr)
        return 1

    print(f"Applied and committed {result['commit'][:8]} on {result['branch']}.")
    if not result["pushed"]:
        print("Not pushed. Re-run with --push to publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
