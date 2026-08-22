"""Tests for warnetech_cli.diagnostics -- the ai-diagnose self-test.

Every check must degrade gracefully (never raise) and diagnose() must
aggregate correctly, including the "skip does not count as failure"
contract that plaintext_fallback_check relies on when no server is up.
"""

import dataclasses
import json
import time

import pytest

from warnetech_cli import diagnostics
from warnetech_cli.commands import Commands
from warnetech_cli.config import Config


class _Cfg(Config):
    def __init__(self, data):
        self.config_path = None
        self.data = data


@pytest.fixture
def config():
    return _Cfg({"server_url": "http://localhost:8080", "api_key": "diagnose-test-key"})


# -- individual checks --------------------------------------------------------


def test_envelope_self_test_round_trips():
    result = diagnostics.envelope_self_test()
    assert result["ok"] is True


def test_retention_health_passes_on_unmodified_thresholds():
    result = diagnostics.retention_health()
    assert result["ok"] is True
    assert result["failed"] == []


def test_retention_health_reports_broken_boundary(monkeypatch):
    """If a tier boundary regresses, this must show up as a named failure,
    not a silent pass."""
    from warnetech_cli.retention import RetentionPolicy

    monkeypatch.setitem(
        RetentionPolicy.TIER_CONFIG, "hot", {**RetentionPolicy.TIER_CONFIG["hot"], "max_age_days": -1}
    )
    result = diagnostics.retention_health()
    assert result["ok"] is False
    assert "hot_at_zero" in result["failed"]


def test_ghost_reconstruction_check_pipeline_is_sound():
    result = diagnostics.ghost_reconstruction_check()
    assert result["ok"] is True
    assert result["reconstruction_pipeline_ok"] is True


def test_ghost_reconstruction_check_flags_the_shape_mismatch():
    """Regression guard for a real finding: GhostStore's own output cannot
    be fed into the reconstruction planner without system/type/time_range."""
    result = diagnostics.ghost_reconstruction_check()
    assert "finding" in result
    assert "system/type/time_range" in result["finding"]


def test_supabase_rpc_check_finds_all_expected_rpcs():
    result = diagnostics.supabase_rpc_check()
    assert result["ok"] is True
    assert set(result["rpcs_present"]) == set(diagnostics.EXPECTED_RPCS)
    assert result["rpcs_missing"] == []


def test_supabase_rpc_check_never_touches_a_live_database(monkeypatch):
    """dry_run must be forced regardless of environment/config."""
    import supabase_schema.utils as sch_utils

    called = []
    monkeypatch.setattr(
        sch_utils, "execute_sql_with_retry", lambda *a, **k: called.append(1)
    )
    diagnostics.supabase_rpc_check()
    assert called == []


def test_operator_manifest_check_passes_without_touching_real_runtime(tmp_path, monkeypatch):
    from warnetech_operator import warnetech_backup_recall as br

    real_runtime = br.RUNTIME
    result = diagnostics.operator_manifest_check()

    assert result["ok"] is True
    assert result["items_verified"] == 1
    # globals must be restored to their real values afterward
    assert br.RUNTIME == real_runtime


def test_operator_manifest_check_restores_globals_even_on_failure(monkeypatch):
    from warnetech_operator import warnetech_backup_recall as br

    real_runtime = br.RUNTIME
    monkeypatch.setattr(br, "create_backup", lambda targets: (_ for _ in ()).throw(RuntimeError("boom")))

    result = diagnostics.operator_manifest_check()

    assert result["ok"] is False
    assert "boom" in result["error"]
    assert br.RUNTIME == real_runtime


def test_config_sanity_reports_missing_keys(config):
    """This dev config has no supabase credentials; that must be reported,
    not swallowed."""
    result = diagnostics.config_sanity(config)
    assert result["ok"] is False
    assert "supabase" in result["error"]


def test_config_sanity_passes_with_all_required_keys():
    cfg = _Cfg(
        {
            "server_url": "http://localhost:8080",
            "api_key": "k",
            "supabase_url": "https://x.supabase.co",
            "supabase_key": "k2",
        }
    )
    assert diagnostics.config_sanity(cfg)["ok"] is True


def test_server_ping_check_reports_unreachable_not_raise(config):
    result = diagnostics.server_ping_check(_client_for(config), config)
    assert result["ok"] is False
    assert result["status"] == "unreachable"


def test_plaintext_fallback_check_skips_when_no_server(config):
    result = diagnostics.plaintext_fallback_check(config)
    assert result["ok"] is None
    assert result["status"] == "skipped"


def test_plaintext_fallback_check_skip_is_not_a_failure(config):
    """A skip must not read as False; diagnose() relies on this distinction
    to avoid flagging overall_ok=False just because no server is running."""
    result = diagnostics.plaintext_fallback_check(config)
    assert result["ok"] is not False


def _client_for(config):
    from warnetech_cli.server_client import ServerClient

    return ServerClient(config)


# -- live-server verification -------------------------------------------------


@pytest.fixture
def live_server():
    from warnetech_server.app import WarnetechServerApp
    from warnetech_server.config import ServerConfig

    cfg = dataclasses.replace(ServerConfig(), api_key="diagnose-test-key", port=0)
    app = WarnetechServerApp(cfg)
    app.start(block=False)
    time.sleep(0.2)
    port = app._server.server_address[1]
    yield port
    app.stop()


def test_plaintext_fallback_check_against_a_real_server_rejects_plaintext(live_server):
    """End to end: the D6 mandatory-envelope guarantee, verified against an
    actual HTTP server rather than a mock."""
    cfg = _Cfg({"server_url": f"http://localhost:{live_server}", "api_key": "diagnose-test-key"})
    result = diagnostics.plaintext_fallback_check(cfg)
    assert result == {"ok": True, "status": 400}


def test_server_ping_check_against_a_real_server(live_server):
    cfg = _Cfg({"server_url": f"http://localhost:{live_server}", "api_key": "diagnose-test-key"})
    result = diagnostics.server_ping_check(_client_for(cfg), cfg)
    assert result["ok"] is True
    assert result["status"] == "pong"


# -- orchestration -------------------------------------------------------------


def test_diagnose_returns_all_eight_checks(config):
    report = diagnostics.diagnose(config, _client_for(config))
    assert set(report["checks"]) == {
        "envelope_self_test",
        "server_ping",
        "retention_health",
        "ghost_reconstruction_check",
        "supabase_rpc_check",
        "operator_manifest_check",
        "plaintext_fallback_check",
        "config_sanity",
    }


def test_diagnose_is_json_serialisable(config):
    report = diagnostics.diagnose(config, _client_for(config))
    json.dumps(report)  # must not raise


def test_diagnose_skip_does_not_sink_overall_ok(config):
    """No server reachable produces a skip (ok=None) on plaintext_fallback_check
    and a real failure (ok=False) on server_ping; overall_ok must reflect
    only genuine failures."""
    report = diagnostics.diagnose(config, _client_for(config))
    assert report["checks"]["plaintext_fallback_check"]["ok"] is None
    assert report["checks"]["server_ping"]["ok"] is False
    assert report["overall_ok"] is False  # server_ping's real False, not the skip


def test_diagnose_survives_a_check_raising(config, monkeypatch):
    """diagnose() must complete a full report even if one check has a bug."""

    def boom(*a, **k):
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(diagnostics._CHECKS, "envelope_self_test", boom)
    report = diagnostics.diagnose(config, _client_for(config))
    assert report["checks"]["envelope_self_test"]["ok"] is False
    assert "simulated failure" in report["checks"]["envelope_self_test"]["error"]
    assert len(report["checks"]) == 8


def test_diagnose_all_ok_against_a_fully_configured_live_server(live_server):
    """With a real server up and full config present, every check should
    read ok (True or a legitimate None skip) -- the closest thing to a
    green-field run this suite can exercise."""
    cfg = _Cfg(
        {
            "server_url": f"http://localhost:{live_server}",
            "api_key": "diagnose-test-key",
            "supabase_url": "https://x.supabase.co",
            "supabase_key": "k",
        }
    )
    report = diagnostics.diagnose(cfg, _client_for(cfg))
    assert report["overall_ok"] is True, report["checks"]


# -- Commands wiring -----------------------------------------------------------


def test_commands_ai_diagnose_delegates_to_diagnostics(config):
    commands = Commands(config)
    report = commands.ai_diagnose()
    assert "overall_ok" in report
    assert "checks" in report


def test_commands_server_ping_still_returns_pong_shape(live_server):
    """Refactoring server_ping to share diagnostics.server_ping_check must
    not change Commands.server_ping()'s own return contract."""
    cfg = _Cfg({"server_url": f"http://localhost:{live_server}", "api_key": "diagnose-test-key"})
    result = Commands(cfg).server_ping()
    assert result["status"] == "pong"
    assert "latency_ms" in result
    assert "timestamp" in result
    assert "ok" not in result  # internal-only field, not part of the public shape


def test_cli_ai_diagnose_command_is_registered():
    from warnetech_cli.main import create_parser

    parser = create_parser()
    args = parser.parse_args(["ai-diagnose"])
    assert args.command == "ai-diagnose"
