"""Tests for the autopatch pipeline.

Each test builds a throwaway git repository, so nothing touches the real
working tree and no network operation is ever attempted.
"""

import subprocess

import pytest

from warnetech_operator import warnetech_autopatch as ap


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repo whose 'test suites' we can make pass or fail on demand."""
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "work")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "app.py").write_text("good code\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")

    monkeypatch.setattr(ap, "LOG_FILE", tmp_path / "logs" / "autopatch.log")
    return r


@pytest.fixture
def good_patch(repo):
    p = repo / "incoming.patch"
    p.write_text(
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1 +1 @@\n"
        "-good code\n"
        "+patched code\n"
    )
    return p


def stub_tests(monkeypatch, python_ok=True, js_ok=True):
    monkeypatch.setattr(
        ap,
        "run_tests",
        lambda repo: {
            "python_ok": python_ok,
            "js_ok": js_ok,
            "all_ok": python_ok and js_ok,
        },
    )


# -- preconditions ----------------------------------------------------------


def test_refuses_dirty_tree(repo, good_patch):
    (repo / "app.py").write_text("uncommitted edit\n")
    with pytest.raises(ap.AutopatchError, match="dirty"):
        ap.autopatch(good_patch, repo=repo)


def test_dirty_tree_check_protects_uncommitted_work(repo, good_patch):
    (repo / "app.py").write_text("uncommitted edit\n")
    with pytest.raises(ap.AutopatchError):
        ap.autopatch(good_patch, repo=repo)
    assert (repo / "app.py").read_text() == "uncommitted edit\n"


def test_missing_patch_raises(repo):
    with pytest.raises(ap.AutopatchError, match="not found"):
        ap.autopatch(repo / "nope.patch", repo=repo)


def test_malformed_patch_rejected(repo):
    bad = repo / "bad.patch"
    bad.write_text("this is not a patch at all\n")
    with pytest.raises(ap.AutopatchError):
        ap.autopatch(bad, repo=repo)


def test_patch_escaping_repo_rejected(repo):
    evil = repo / "evil.patch"
    evil.write_text(
        "diff --git a/../../escaped.txt b/../../escaped.txt\n"
        "--- /dev/null\n"
        "+++ b/../../escaped.txt\n"
        "@@ -0,0 +1 @@\n"
        "+pwned\n"
    )
    with pytest.raises(ap.AutopatchError):
        ap.autopatch(evil, repo=repo)


# -- the gate ---------------------------------------------------------------


def test_failing_tests_revert_the_patch(repo, good_patch, monkeypatch):
    """The defect this tool exists to avoid: a failed patch left applied."""
    stub_tests(monkeypatch, python_ok=False)
    result = ap.autopatch(good_patch, repo=repo)

    assert result["applied"] is False
    assert result["reverted"] is True
    assert (repo / "app.py").read_text() == "good code\n"


def test_failing_tests_leave_no_commit(repo, good_patch, monkeypatch):
    before = ap.head_commit(repo)
    stub_tests(monkeypatch, js_ok=False)
    ap.autopatch(good_patch, repo=repo)
    assert ap.head_commit(repo) == before


def test_failing_tests_leave_clean_tree(repo, good_patch, monkeypatch):
    stub_tests(monkeypatch, python_ok=False)
    ap.autopatch(good_patch, repo=repo)
    assert ap.is_dirty(repo) is False


def test_js_failure_alone_reverts(repo, good_patch, monkeypatch):
    stub_tests(monkeypatch, python_ok=True, js_ok=False)
    result = ap.autopatch(good_patch, repo=repo)
    assert result["reverted"] is True


# -- success path -----------------------------------------------------------


def test_passing_tests_commit_the_patch(repo, good_patch, monkeypatch):
    stub_tests(monkeypatch)
    result = ap.autopatch(good_patch, repo=repo)

    assert result["applied"] is True
    assert (repo / "app.py").read_text() == "patched code\n"
    assert result["commit"]


def test_commit_message_is_customisable(repo, good_patch, monkeypatch):
    stub_tests(monkeypatch)
    ap.autopatch(good_patch, repo=repo, message="fix: something specific")
    log = git(repo, "log", "-1", "--pretty=%s").stdout.strip()
    assert log == "fix: something specific"


def test_only_patched_files_are_staged(repo, good_patch, monkeypatch):
    """git add -A would sweep in unrelated files; only the patch's files
    should be committed."""
    stub_tests(monkeypatch)
    (repo / "unrelated.txt").write_text("do not commit me\n")
    ap.autopatch(good_patch, repo=repo)

    committed = git(repo, "show", "--name-only", "--pretty=", "HEAD").stdout.split()
    assert "app.py" in committed
    assert "unrelated.txt" not in committed


# -- publishing -------------------------------------------------------------


def test_does_not_push_by_default(repo, good_patch, monkeypatch):
    stub_tests(monkeypatch)
    pushed = []
    monkeypatch.setattr(ap, "push", lambda r, b: pushed.append(b))
    result = ap.autopatch(good_patch, repo=repo)
    assert result["pushed"] is False
    assert pushed == []


def test_pushes_only_when_asked(repo, good_patch, monkeypatch):
    stub_tests(monkeypatch)
    pushed = []
    monkeypatch.setattr(ap, "push", lambda r, b: pushed.append(b))
    result = ap.autopatch(good_patch, repo=repo, do_push=True)
    assert result["pushed"] is True
    assert pushed == ["work"]


@pytest.mark.parametrize("branch", ["main", "master"])
def test_push_refuses_protected_branches(repo, branch):
    with pytest.raises(ap.AutopatchError, match="protected"):
        ap.push(repo, branch)


# -- dry run ----------------------------------------------------------------


def test_dry_run_validates_without_applying(repo, good_patch):
    result = ap.autopatch(good_patch, repo=repo, dry_run=True)
    assert result["dry_run"] is True
    assert result["files"] == ["app.py"]
    assert (repo / "app.py").read_text() == "good code\n"


def test_dry_run_still_rejects_bad_patch(repo):
    bad = repo / "bad.patch"
    bad.write_text("garbage\n")
    with pytest.raises(ap.AutopatchError):
        ap.autopatch(bad, repo=repo, dry_run=True)


# -- CLI --------------------------------------------------------------------


def test_cli_returns_nonzero_on_failed_tests(repo, good_patch, monkeypatch):
    stub_tests(monkeypatch, python_ok=False)
    assert ap.main([str(good_patch), "--repo", str(repo)]) == 1


def test_cli_returns_zero_on_success(repo, good_patch, monkeypatch):
    stub_tests(monkeypatch)
    assert ap.main([str(good_patch), "--repo", str(repo)]) == 0


def test_cli_dry_run(repo, good_patch, capsys):
    assert ap.main([str(good_patch), "--repo", str(repo), "--dry-run"]) == 0
    assert "valid" in capsys.readouterr().out
