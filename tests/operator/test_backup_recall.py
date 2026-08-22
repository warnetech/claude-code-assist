"""Tests for operator backup/recall.

Every test redirects the module's runtime paths into tmp_path, so nothing
touches the real ~/.warnetech or the working repository.
"""

import json

import pytest

from warnetech_operator import warnetech_backup_recall as br


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    """Point the module at a throwaway runtime and fake repo."""
    rt = tmp_path / ".warnetech"
    repo = tmp_path / "claude-command-cli"
    (rt / "logs").mkdir(parents=True)
    (rt / "backups").mkdir(parents=True)
    (repo / "warnetech_server").mkdir(parents=True)
    (repo / "warnetech_server" / "app.py").write_text("real source")

    monkeypatch.setattr(br, "RUNTIME", rt)
    monkeypatch.setattr(br, "BACKUP_DIR", rt / "backups")
    monkeypatch.setattr(br, "STATE_FILE", rt / "state.json")
    monkeypatch.setattr(br, "LOG_FILE", rt / "logs" / "backup_recall.log")
    monkeypatch.setattr(br, "_repo_root", lambda: repo)

    (rt / "state.json").write_text(json.dumps({"last_backup": None, "marker": "live"}))
    return {"rt": rt, "repo": repo, "targets": [repo / "warnetech_server", rt / "state.json"]}


# -- state ------------------------------------------------------------------


def test_load_state_tolerates_missing_file(runtime):
    runtime["rt"].joinpath("state.json").unlink()
    assert br.load_state() == br.DEFAULT_STATE


def test_load_state_tolerates_corrupt_json(runtime):
    runtime["rt"].joinpath("state.json").write_text("{not json")
    assert br.load_state() == br.DEFAULT_STATE


def test_log_creates_directory(runtime, tmp_path):
    br.LOG_FILE.parent.rmdir()
    br.log("hello")
    assert "hello" in br.LOG_FILE.read_text()


# -- backup -----------------------------------------------------------------


def test_default_targets_exclude_git_tracked_source(runtime):
    """Source is versioned by git; restoring a backup over the working tree
    would silently revert committed work. Backups cover runtime state only."""
    targets = [str(t) for t in br.backup_targets()]
    assert all("claude-command-cli" not in t for t in targets)
    assert any(t.endswith("state.json") for t in targets)


def test_backup_writes_manifest(runtime):
    path = br.create_backup(runtime["targets"])
    manifest = json.loads((path / br.MANIFEST_NAME).read_text())
    assert len(manifest["items"]) == 2
    assert all("checksum" in i and "origin" in i for i in manifest["items"])


def test_backup_records_original_paths(runtime):
    path = br.create_backup(runtime["targets"])
    manifest = json.loads((path / br.MANIFEST_NAME).read_text())
    origins = {i["name"]: i["origin"] for i in manifest["items"]}
    # state.json must record ~/.warnetech, NOT the repo directory
    assert origins["state.json"] == str(runtime["rt"] / "state.json")


def test_backup_skips_missing_targets(runtime):
    path = br.create_backup([runtime["repo"] / "does-not-exist"])
    manifest = json.loads((path / br.MANIFEST_NAME).read_text())
    assert manifest["items"] == []


def test_backup_excludes_pycache(runtime):
    cache = runtime["repo"] / "warnetech_server" / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_text("junk")
    path = br.create_backup(runtime["targets"])
    assert not (path / "warnetech_server" / "__pycache__").exists()


def test_backup_updates_state(runtime):
    br.create_backup(runtime["targets"])
    assert br.load_state()["last_backup"] is not None


def test_list_backups(runtime):
    assert br.list_backups() == []
    name = br.create_backup(runtime["targets"]).name
    assert name in br.list_backups()


# -- integrity --------------------------------------------------------------


def test_verify_passes_on_intact_backup(runtime):
    name = br.create_backup(runtime["targets"]).name
    assert br.verify_backup(name)["all_ok"] is True


def test_verify_detects_tampering(runtime):
    path = br.create_backup(runtime["targets"])
    (path / "warnetech_server" / "app.py").write_text("TAMPERED")
    assert br.verify_backup(path.name)["all_ok"] is False


def test_recall_refuses_corrupt_backup(runtime):
    path = br.create_backup(runtime["targets"])
    (path / "warnetech_server" / "app.py").write_text("TAMPERED")
    with pytest.raises(ValueError, match="checksum mismatch"):
        br.recall_backup(path.name)


def test_corrupt_backup_does_not_overwrite_source(runtime):
    path = br.create_backup(runtime["targets"])
    (path / "warnetech_server" / "app.py").write_text("TAMPERED")
    with pytest.raises(ValueError):
        br.recall_backup(path.name)
    live = runtime["repo"] / "warnetech_server" / "app.py"
    assert live.read_text() == "real source"


# -- recall -----------------------------------------------------------------


def test_recall_restores_state_to_runtime_not_repo(runtime):
    """Regression: state.json was restored into the repo directory, so the
    live ~/.warnetech/state.json was never actually recovered."""
    name = br.create_backup(runtime["targets"]).name
    br.STATE_FILE.write_text(json.dumps({"marker": "clobbered"}))

    br.recall_backup(name)

    assert not (runtime["repo"] / "state.json").exists()
    assert json.loads(br.STATE_FILE.read_text())["marker"] == "live"


def test_recall_restores_directory_contents(runtime):
    name = br.create_backup(runtime["targets"]).name
    live = runtime["repo"] / "warnetech_server" / "app.py"
    live.write_text("broken edit")

    br.recall_backup(name)
    assert live.read_text() == "real source"


def test_recall_records_last_recall(runtime):
    name = br.create_backup(runtime["targets"]).name
    br.recall_backup(name)
    assert br.load_state()["last_recall"] == name


def test_dry_run_changes_nothing(runtime):
    name = br.create_backup(runtime["targets"]).name
    live = runtime["repo"] / "warnetech_server" / "app.py"
    live.write_text("broken edit")

    plan = br.recall_backup(name, dry_run=True)

    assert plan["dry_run"] is True
    assert len(plan["planned"]) == 2
    assert live.read_text() == "broken edit"


def test_recall_missing_backup_raises(runtime):
    with pytest.raises(ValueError, match="not found"):
        br.recall_backup("backup_does_not_exist")


def test_recall_without_manifest_refuses(runtime):
    legacy = br.BACKUP_DIR / "backup_legacy"
    legacy.mkdir()
    (legacy / "state.json").write_text("{}")
    with pytest.raises(ValueError, match="no manifest"):
        br.recall_backup("backup_legacy")


@pytest.mark.parametrize("name", ["../escape", "../../etc", "sub/../../out"])
def test_path_traversal_rejected(runtime, name):
    with pytest.raises(ValueError, match="escapes"):
        br.recall_backup(name)


# -- CLI --------------------------------------------------------------------


def test_cli_backup_and_list(runtime, capsys):
    assert br.main(["backup"]) == 0
    assert br.main(["list"]) == 0
    assert "backup_" in capsys.readouterr().out


def test_cli_verify_returns_nonzero_on_tamper(runtime):
    path = br.create_backup(runtime["targets"])
    (path / "warnetech_server" / "app.py").write_text("TAMPERED")
    assert br.main(["verify", path.name]) == 1


def test_cli_recall_dry_run_needs_no_confirmation(runtime, capsys):
    name = br.create_backup(runtime["targets"]).name
    assert br.main(["recall", name, "--dry-run"]) == 0
    assert "planned" in capsys.readouterr().out
