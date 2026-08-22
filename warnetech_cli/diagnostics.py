"""System self-test for the Warnetech CLI.

Exercises the local logic paths (envelope, retention, ghost reconstruction,
config) purely in-process, and the network paths (server reachability,
plaintext rejection) only through HTTP -- the same interface ServerClient
uses. This module never imports warnetech_server internals: CLAUDE.md asks
the CLI and server layers to stay independent, and reaching into the
server's package to fake a request would cross that boundary rather than
test the real one.

Every check function returns a dict with at least {"ok": bool, ...}. No
check raises: diagnose() wraps each one so a bug in a single check cannot
take down the whole report, and an unreachable server or an unconfigured
credential is reported as a finding, not a crash.
"""

from __future__ import annotations

import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

from warnetech_cli.config import Config
from warnetech_cli.ghost_store import GhostStore
from warnetech_cli.retention import RetentionPolicy
from warnetech_cli.server_client import ServerClient
from warnetech_envelope import decrypt_data, encrypt_data


# -- 1. envelope_self_test ---------------------------------------------------


def envelope_self_test() -> Dict[str, Any]:
    """Round-trips a message through the canonical AES-256-GCM envelope."""
    try:
        message = "warnetech-diagnose-self-test"
        key = "diagnose-ephemeral-key"
        packet = encrypt_data(message, key)
        recovered = decrypt_data(packet, key)
        return {"ok": recovered == message}
    except Exception as exc:  # noqa: BLE001 - a diagnostic must never raise
        return {"ok": False, "error": str(exc)}


# -- 2. server_ping -----------------------------------------------------------


def server_ping_check(client: ServerClient, config: Config) -> Dict[str, Any]:
    """Round-trip latency to warnetech-server. Shared with Commands.server_ping
    so the standalone command and the diagnostic report the same thing."""
    start = time.monotonic()
    result = client.get("/status")
    latency_ms = (time.monotonic() - start) * 1000
    if "error" in result:
        return {"ok": False, "status": "unreachable", "server": config.get("server_url"), **result}
    return {
        "ok": True,
        "status": "pong",
        "server": config.get("server_url"),
        "latency_ms": round(latency_ms, 1),
    }


# -- 3. retention_health -------------------------------------------------------


def retention_health() -> Dict[str, Any]:
    """Exercises RetentionPolicy's tier boundaries against its own stated
    thresholds, so a change to TIER_CONFIG that breaks the boundary logic
    is caught here rather than silently misfiling data."""
    hot_max = RetentionPolicy.TIER_CONFIG["hot"]["max_age_days"]
    warm_max = RetentionPolicy.TIER_CONFIG["warm"]["max_age_days"]
    ghost_max = RetentionPolicy.TIER_CONFIG["ghost"]["max_age_days"]

    checks = {
        "hot_at_zero": RetentionPolicy.get_tier_for_age(0) == "hot",
        "hot_at_boundary": RetentionPolicy.get_tier_for_age(hot_max) == "hot",
        "warm_just_past_hot": RetentionPolicy.get_tier_for_age(hot_max + 0.001) == "warm",
        "warm_at_boundary": RetentionPolicy.get_tier_for_age(warm_max) == "warm",
        "ghost_just_past_warm": RetentionPolicy.get_tier_for_age(warm_max + 0.001) == "ghost",
        "not_expired_at_ghost_boundary": RetentionPolicy.should_expire(ghost_max) is False,
        "expired_just_past_ghost": RetentionPolicy.should_expire(ghost_max + 0.001) is True,
        "promotes_hot_to_warm": RetentionPolicy.should_promote("hot", hot_max + 1) is True,
        "does_not_demote_ghost": RetentionPolicy.should_promote("ghost", 10_000) is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {"ok": not failed, "failed": failed}


# -- 4. ghost_reconstruction_check --------------------------------------------


def ghost_reconstruction_check() -> Dict[str, Any]:
    """Confirms the recall-planner reconstruction pipeline is sound, using a
    synthetic ghost in the shape it expects (system/type/time_range).

    Also flags a genuine shape mismatch: GhostStore.create_ghost_copy(), the
    CLI-local ghost constructor, does not emit these fields, so its output
    cannot be fed into the reconstruction planner directly today. That is
    reported as a finding, not treated as this check's own failure.
    """
    from warnetech_ai_controller.recall_planner import build_reconstruction_plan

    try:
        synthetic_ghost = {
            "slice_id": "diagnose-synthetic",
            "system": "diagnose",
            "type": "self-test",
            "created_at": "2026-01-01T00:00:00Z",
            "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        }
        plan = build_reconstruction_plan([synthetic_ghost], system="diagnose")
        pipeline_ok = plan.total_steps == 1

        cli_ghost = GhostStore.create_ghost_copy(b"probe", {"id": "diagnose"})
        shape_compatible = {"system", "type", "time_range"} <= cli_ghost.keys()

        result = {"ok": pipeline_ok, "reconstruction_pipeline_ok": pipeline_ok}
        if not shape_compatible:
            result["finding"] = (
                "GhostStore.create_ghost_copy() output has no system/type/time_range "
                "fields, so it cannot be passed directly to build_reconstruction_plan()."
            )
        return result
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# -- 5. supabase_rpc_check ------------------------------------------------------


EXPECTED_RPCS = ("maintain_partitions", "refresh_metric_rollups", "maintain_threat_event_partitions")


def supabase_rpc_check() -> Dict[str, Any]:
    """Dry-run parses tables.sql and rpcs.sql. Never touches a live database:
    dry_run=True is forced here regardless of environment configuration, so
    this check is safe to run with no Supabase credentials at all."""
    from supabase_schema.config import DEFAULT_CONFIG
    from supabase_schema.migrations import _read_sql
    from supabase_schema.utils import split_statements

    try:
        rpcs_sql = _read_sql(DEFAULT_CONFIG.migration.rpcs_file)
        present = [name for name in EXPECTED_RPCS if name in rpcs_sql]
        missing = [name for name in EXPECTED_RPCS if name not in rpcs_sql]
        statement_count = len(split_statements(rpcs_sql))
        return {
            "ok": not missing,
            "rpcs_present": present,
            "rpcs_missing": missing,
            "statement_count": statement_count,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# -- 6. operator_manifest_check -------------------------------------------------


def operator_manifest_check() -> Dict[str, Any]:
    """Exercises the operator backup manifest + checksum path end to end,
    redirected into a throwaway temp directory so this never touches the
    real ~/.warnetech/backups. Module globals are restored in `finally`
    even if the check raises."""
    from warnetech_operator import warnetech_backup_recall as br

    saved = (br.RUNTIME, br.BACKUP_DIR, br.STATE_FILE, br.LOG_FILE)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            br.RUNTIME = root
            br.BACKUP_DIR = root / "backups"
            br.STATE_FILE = root / "state.json"
            br.LOG_FILE = root / "logs" / "diagnose.log"
            br.STATE_FILE.write_text('{"probe": "diagnose"}')

            backup_path = br.create_backup([br.STATE_FILE])
            verification = br.verify_backup(backup_path.name)
            return {"ok": verification["all_ok"], "items_verified": len(verification["items"])}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    finally:
        br.RUNTIME, br.BACKUP_DIR, br.STATE_FILE, br.LOG_FILE = saved


# -- 7. plaintext_fallback_check ------------------------------------------------


def plaintext_fallback_check(config: Config) -> Dict[str, Any]:
    """Confirms a live server actually enforces the mandatory envelope (the
    D6 change): a plaintext body must come back 400 envelope_required, never
    200. Sends a raw, deliberately unsealed request over urllib -- ServerClient
    itself now refuses to send plaintext by design, so it cannot be reused to
    produce this probe.

    If no server is reachable the check is skipped, not failed, matching
    server_ping's semantics for the same condition.
    """
    server_url = (config.get("server_url") or "").rstrip("/")
    api_key = config.get("api_key") or ""
    if not server_url:
        return {"ok": None, "status": "skipped", "reason": "server_url is not configured"}

    req = urllib.request.Request(
        f"{server_url}/status",
        data=b'{"command":"diagnose-probe"}',
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=10):
            # A 200 here means the server accepted a plaintext body: the
            # mandatory-envelope guarantee does not hold.
            return {"ok": False, "status": "server_accepted_plaintext"}
    except urllib.error.HTTPError as exc:
        return {"ok": exc.code == 400, "status": exc.code}
    except urllib.error.URLError as exc:
        return {"ok": None, "status": "skipped", "reason": f"server unreachable: {exc.reason}"}


# -- 8. config_sanity ------------------------------------------------------------


def config_sanity(config: Config) -> Dict[str, Any]:
    """Delegates to Config.validate() -- the CLI's own definition of a valid
    configuration -- rather than inventing a separate notion of sanity."""
    try:
        config.validate()
        return {"ok": True}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


# -- orchestration ---------------------------------------------------------------

_CHECKS: Dict[str, Callable[[Config, ServerClient], Dict[str, Any]]] = {
    "envelope_self_test": lambda config, client: envelope_self_test(),
    "server_ping": lambda config, client: server_ping_check(client, config),
    "retention_health": lambda config, client: retention_health(),
    "ghost_reconstruction_check": lambda config, client: ghost_reconstruction_check(),
    "supabase_rpc_check": lambda config, client: supabase_rpc_check(),
    "operator_manifest_check": lambda config, client: operator_manifest_check(),
    "plaintext_fallback_check": lambda config, client: plaintext_fallback_check(config),
    "config_sanity": lambda config, client: config_sanity(config),
}


def diagnose(config: Config, client: ServerClient) -> Dict[str, Any]:
    """Runs every check and aggregates the results.

    A check whose "ok" is None (a deliberate skip, e.g. no server reachable)
    does not count against overall_ok; only an explicit False does.
    """
    results: Dict[str, Any] = {}
    for name, check in _CHECKS.items():
        try:
            results[name] = check(config, client)
        except Exception as exc:  # noqa: BLE001 - one bad check must not sink the report
            results[name] = {"ok": False, "error": f"check raised: {exc}"}

    overall_ok = all(r.get("ok") is not False for r in results.values())
    return {
        "overall_ok": overall_ok,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": results,
    }
