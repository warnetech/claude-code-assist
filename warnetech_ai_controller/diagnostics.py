def ai_diagnose():
    report = {}

    # 1. Envelope integrity
    try:
        from warnetech_envelope import seal, open as envelope_open
        key = b"0" * 32
        msg = b"diag"
        env = seal(key, msg)
        ok = envelope_open(key, env) == msg
        report["envelope"] = "ok" if ok else "fail"
    except Exception as e:
        report["envelope"] = f"error: {e}"

    # 2. Server reachability
    try:
        from warnetech_cli.commands import Commands
        from warnetech_cli.config import Config
        cfg = Config.from_env()
        cmd = Commands(cfg)
        res = cmd.server_ping()
        report["server"] = res
    except Exception as e:
        report["server"] = f"error: {e}"

    # 3. Retention engine
    try:
        from warnetech_control_plane.retention_engine import RetentionEngine
        r = RetentionEngine()
        report["retention"] = {
            "slice_count": len(r.slices),
            "top_scores": sorted(r.scores, reverse=True)[:5],
        }
    except Exception as e:
        report["retention"] = f"error: {e}"

    # 4. Ghost engine
    try:
        from warnetech_control_plane.ghost_engine import GhostEngine
        g = GhostEngine()
        ghost = g.reconstruct()
        report["ghost_reconstruction"] = "ok" if ghost else "fail"
    except Exception as e:
        report["ghost_reconstruction"] = f"error: {e}"

    # 5. Supabase RPC health
    try:
        from supabase_schema.database import get_client
        client = get_client()
        ping = client.table("threat_events").select("*").limit(1).execute()
        report["supabase"] = "ok" if ping.data else "fail"
    except Exception as e:
        report["supabase"] = f"error: {e}"

    # 6. Manifest
    import os
    manifest_path = os.path.expanduser("~/.warnetech/manifest.json")
    report["manifest"] = "present" if os.path.exists(manifest_path) else "absent"

    # 7. Plaintext fallback
    report["plaintext_fallback"] = "enabled"

    return report
