#!/usr/bin/env python3
"""Operator backup and recall for the Warnetech runtime.

Implements steps 1-4 of the recovery protocol in
docs/AI-FIREWALL-COMPLETE-REFERENCE.txt: export, store, rehydrate, and
validate checksums.

Each backup carries a manifest recording every item's ORIGINAL absolute
path. Recall restores from the manifest, so a file backed up from
~/.warnetech returns to ~/.warnetech rather than being dropped into the
repository directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

RUNTIME = Path.home() / ".warnetech"
BACKUP_DIR = RUNTIME / "backups"
STATE_FILE = RUNTIME / "state.json"
LOG_FILE = RUNTIME / "logs" / "backup_recall.log"
MANIFEST_NAME = "manifest.json"

DEFAULT_STATE = {"last_backup": None, "last_recall": None, "operator_events": []}

# Directories excluded from backups: regenerable, and copying them is slow.
EXCLUDE = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "node_modules")


def _repo_root() -> Path:
    return Path.home() / "claude-command-cli"


def backup_targets() -> list[Path]:
    """Runtime state only.

    Source directories are deliberately excluded: git already versions them,
    so restoring a backup over the working tree would silently revert
    committed work. Use `git checkout` to recover source. What is unique to
    this machine, and therefore worth backing up, is the runtime state.
    """
    return [
        STATE_FILE,
        RUNTIME / "logs",
        RUNTIME / "tmp",
    ]


# -- state ------------------------------------------------------------------


def load_state() -> dict:
    """Read operator state, tolerating a missing or corrupt file."""
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_STATE)


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log(event: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as handle:
        handle.write(f"[{ts}] {event}\n")


# -- integrity --------------------------------------------------------------


def checksum(path: Path) -> str:
    """SHA-256 of a file, or of a directory's sorted file contents."""
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        if "__pycache__" in child.parts:
            continue
        digest.update(str(child.relative_to(path)).encode())
        digest.update(child.read_bytes())
    return digest.hexdigest()


def _resolve_backup(backup_name: str) -> Path:
    """Resolve a backup name, refusing anything outside BACKUP_DIR."""
    candidate = (BACKUP_DIR / backup_name).resolve()
    if not str(candidate).startswith(str(BACKUP_DIR.resolve())):
        raise ValueError(f"backup name escapes the backup directory: {backup_name}")
    return candidate


# -- backup -----------------------------------------------------------------


def create_backup(targets: Optional[list[Path]] = None) -> Path:
    """Copy each target into a timestamped backup with a manifest."""
    ts = int(time.time())
    backup_path = BACKUP_DIR / f"backup_{ts}"
    backup_path.mkdir(parents=True, exist_ok=True)

    manifest = {"created_at": ts, "items": []}

    for target in targets if targets is not None else backup_targets():
        if not target.exists():
            continue
        destination = backup_path / target.name
        if target.is_file():
            shutil.copy2(target, destination)
        else:
            shutil.copytree(target, destination, ignore=EXCLUDE)
        manifest["items"].append(
            {
                "name": target.name,
                "origin": str(target),
                "is_file": target.is_file(),
                "checksum": checksum(destination),
            }
        )

    (backup_path / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2))

    state = load_state()
    state["last_backup"] = ts
    save_state(state)

    log(f"Backup created: {backup_path} ({len(manifest['items'])} items)")
    return backup_path


def list_backups() -> list[str]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(p.name for p in BACKUP_DIR.iterdir() if p.is_dir())


def verify_backup(backup_name: str) -> dict:
    """Re-checksum every item and report mismatches without restoring."""
    backup_path = _resolve_backup(backup_name)
    manifest_file = backup_path / MANIFEST_NAME
    if not manifest_file.exists():
        raise ValueError(f"backup has no manifest: {backup_name}")

    manifest = json.loads(manifest_file.read_text())
    results = []
    for item in manifest["items"]:
        stored = backup_path / item["name"]
        ok = stored.exists() and checksum(stored) == item["checksum"]
        results.append({"name": item["name"], "ok": ok})

    return {"backup": backup_name, "all_ok": all(r["ok"] for r in results), "items": results}


# -- recall -----------------------------------------------------------------


def recall_backup(backup_name: str, dry_run: bool = False) -> dict:
    """Restore a backup to each item's recorded origin.

    Refuses to run if any checksum fails, so a corrupt backup cannot
    overwrite good source. Pass dry_run=True to see the plan without
    touching the filesystem.
    """
    backup_path = _resolve_backup(backup_name)
    if not backup_path.exists():
        raise ValueError(f"Backup not found: {backup_name}")

    manifest_file = backup_path / MANIFEST_NAME
    if not manifest_file.exists():
        raise ValueError(
            f"Backup {backup_name} has no manifest and cannot be safely restored"
        )

    verification = verify_backup(backup_name)
    if not verification["all_ok"]:
        failed = [r["name"] for r in verification["items"] if not r["ok"]]
        raise ValueError(f"checksum mismatch, refusing to restore: {failed}")

    manifest = json.loads(manifest_file.read_text())
    planned = [{"name": i["name"], "restores_to": i["origin"]} for i in manifest["items"]]

    if dry_run:
        return {"dry_run": True, "backup": backup_name, "planned": planned}

    for item in manifest["items"]:
        source = backup_path / item["name"]
        target = Path(item["origin"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)
        if item["is_file"]:
            shutil.copy2(source, target)
        else:
            shutil.copytree(source, target)

    # Reloaded after restore: state.json is itself a restored item.
    state = load_state()
    state["last_recall"] = backup_name
    save_state(state)

    log(f"Backup recalled: {backup_name} ({len(manifest['items'])} items)")
    return {"dry_run": False, "backup": backup_name, "restored": planned}


# -- CLI --------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="warnetech-backup-recall")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("backup", help="create a new backup")
    sub.add_parser("list", help="list available backups")

    verify = sub.add_parser("verify", help="check a backup's checksums")
    verify.add_argument("name")

    recall = sub.add_parser("recall", help="restore a backup")
    recall.add_argument("name")
    recall.add_argument(
        "--dry-run", action="store_true", help="show what would be restored"
    )
    recall.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompt"
    )

    args = parser.parse_args(argv)

    if args.command == "backup":
        print(f"Backup created at: {create_backup()}")
        return 0

    if args.command == "list":
        names = list_backups()
        print("\n".join(names) if names else "No backups found.")
        return 0

    if args.command == "verify":
        result = verify_backup(args.name)
        print(json.dumps(result, indent=2))
        return 0 if result["all_ok"] else 1

    if args.command == "recall":
        if args.dry_run:
            print(json.dumps(recall_backup(args.name, dry_run=True), indent=2))
            return 0
        if not args.yes:
            plan = recall_backup(args.name, dry_run=True)
            print("This will OVERWRITE:")
            for item in plan["planned"]:
                print(f"  {item['restores_to']}")
            if input("Proceed? [y/N] ").strip().lower() != "y":
                print("Aborted.")
                return 1
        recall_backup(args.name)
        print("Backup recalled.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
