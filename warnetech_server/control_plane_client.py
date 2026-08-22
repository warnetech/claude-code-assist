"""Client for warnetech-control-plane: signature queries, scoring requests,
learning triggers, recovery triggers, retention policy updates, and slice
and ghost operations.

Per docs/WARNETECH-CANONICAL-WIRING-SPEC.txt decision 1: this calls
warnetech_control_plane in-process via direct Python imports, not HTTP.
There is no network hop, no serialization boundary, and no separate
service to deploy or secure — the two packages share one process and one
in-memory ControlPlaneState.

Every public method still fails soft: an exception inside the
control-plane call is logged and turned into None, so a bug in one
operation degrades that single API response (routes.py returns 502) rather
than taking the whole server down. What no longer exists is a *reachability*
failure mode — if warnetech_control_plane fails to import at all, that is a
packaging error, not a transient condition, so it is raised immediately at
construction instead of being caught per-call.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .config import ServerConfig
from .logging import get_logger, log_control_plane_call

logger = get_logger(__name__)


class ControlPlaneClient:
    def __init__(self, config: ServerConfig) -> None:
        self._config = config

        try:
            import warnetech_control_plane as wcp
        except ImportError as exc:
            raise RuntimeError(
                "warnetech_control_plane is required for in-process control-plane wiring "
                "(see docs/WARNETECH-CANONICAL-WIRING-SPEC.txt decision 1); "
                "ensure it is importable alongside warnetech_server"
            ) from exc

        # warnetech_control_plane reads SUPABASE_URL/SUPABASE_KEY independently
        # of warnetech_server's own ServerConfig.database — per wiring spec
        # decision 2, both point at the same Supabase project via those two
        # environment variables, so no explicit passthrough is needed here.
        self._wcp = wcp
        cp_config = wcp.ControlPlaneConfig()
        self._cp_config = cp_config
        self._state = wcp.ControlPlaneState(cp_config)
        self._database = wcp.SupabaseDatabase(cp_config)

        self._signatures = wcp.SignatureEngine(self._state, self._database, cp_config)
        self._scoring = wcp.ScoringEngine(cp_config)
        self._learning = wcp.LearningEngine(self._state, self._signatures, cp_config)
        self._recovery = wcp.RecoveryEngine(self._state, self._signatures, self._database, cp_config)
        self._retention = wcp.RetentionEngine(cp_config, database=self._database)
        self._slicer = wcp.SliceEngine(cp_config)
        self._ghost = wcp.GhostEngine(cp_config)

        # One-time cache warm at startup. This mirrors the JS Worker's
        # hourly-cron warm, but running synchronously here is fine — it is a
        # one-time startup cost, not a per-request one.
        self._signatures.sync_cache()

    def _call(self, operation: str, fn) -> Optional[Any]:
        start = time.monotonic()
        try:
            result = fn()
            log_control_plane_call(logger, operation, True, (time.monotonic() - start) * 1000)
            return result
        except Exception as exc:  # noqa: BLE001 - one bad call must not take the server down
            logger.error("control-plane call failed", operation=operation, error=str(exc))
            log_control_plane_call(logger, operation, False, (time.monotonic() - start) * 1000)
            return None

    # -- signatures / scoring -----------------------------------------------------

    def query_signatures(self, attack_type: Optional[str] = None) -> list[dict]:
        def op():
            signatures = self._state.all_signatures()
            if attack_type:
                signatures = [s for s in signatures if s.get("attack_type") == attack_type]
            return signatures
        return self._call("query_signatures", op) or []

    def request_score(self, payload: dict) -> Optional[dict]:
        def op():
            text = payload.get("text", "")
            matches = self._signatures.match(text)
            signature_score = matches[0]["score"] if matches else 0.0
            result = self._scoring.score(
                signature_score=signature_score,
                behavioral_score=payload.get("behavioral_score", 0.0),
                anomaly_score=payload.get("anomaly_score", 0.0),
                adaptation_multiplier=payload.get("adaptation_multiplier", 1.0),
            )
            return {
                "total": result.total,
                "threat_level": result.threat_level,
                "signature_score": result.signature_score,
                "behavioral_score": result.behavioral_score,
                "anomaly_score": result.anomaly_score,
                "matched_signature_ids": [m["id"] for m in matches],
            }
        return self._call("request_score", op)

    # -- learning / recovery ----------------------------------------------------------

    def trigger_learning(self, attack_type: str, pattern: str, matched_ids: list[str], true_positive: bool) -> Optional[dict]:
        def op():
            result = self._learning.report_outcome(attack_type, pattern, matched_ids, true_positive)
            if result is None:
                return None
            return result.to_dict() if hasattr(result, "to_dict") else result
        return self._call("trigger_learning", op)

    def trigger_recovery(self, incident_id: str) -> Optional[dict]:
        def op():
            return self._recovery.run(incident_id).to_dict()
        return self._call("trigger_recovery", op)

    # -- retention -------------------------------------------------------------------

    def update_retention_policy(self, policy: dict) -> Optional[dict]:
        def op():
            # RetentionPolicy is a frozen dataclass on ControlPlaneConfig, not
            # mutable state — recording the request here rather than silently
            # no-op'ing, since actually changing it requires a config reload.
            return {
                "requested": policy,
                "applied": False,
                "note": "retention policy is config-driven (ControlPlaneConfig.retention); update config and restart to apply",
            }
        return self._call("update_retention_policy", op)

    def get_retention_policy(self) -> Optional[dict]:
        def op():
            r = self._cp_config.retention
            return {
                "hot_tier_hours": r.hot_tier_hours,
                "warm_tier_days": r.warm_tier_days,
                "ghost_tier_days": r.ghost_tier_days,
                "downsample_factor": r.downsample_factor,
            }
        return self._call("get_retention_policy", op)

    # -- slice / ghost -----------------------------------------------------------------

    def slice_operation(self, params: dict) -> Optional[dict]:
        def op():
            sl = self._slicer.build_slice(
                slice_id=params["slice_id"],
                domain=params["domain"],
                records=params.get("records", []),
                time_start=params["time_start"],
                time_end=params["time_end"],
                compress=params.get("compress", True),
            )
            return sl.metadata.to_dict()
        return self._call("slice_operation", op)

    def compress_operation(self, params: dict) -> Optional[dict]:
        def op():
            data = params.get("data", "").encode("utf-8")
            compressed = self._slicer.compress(data)
            return {"original_bytes": len(data), "compressed_bytes": len(compressed)}
        return self._call("compress_operation", op)

    def ghost_create(self, params: dict) -> Optional[dict]:
        """Accepts slice identifiers/metadata (`slice_id`, `domain`,
        `records`, `time_start`, `time_end`); slicer.build_slice() both
        slices and compresses in one call (compress=True by default), so
        the resulting Slice.body is already the compressed payload
        ghost_engine.create_ghost_copy() expects.
        """
        def op():
            sl = self._slicer.build_slice(
                slice_id=params["slice_id"],
                domain=params["domain"],
                records=params.get("records", []),
                time_start=params["time_start"],
                time_end=params["time_end"],
                compress=params.get("compress", True),
            )
            record = self._wcp.create_ghost_copy(
                sl.metadata, sl.body, config=self._cp_config,
                encryption_key_id=params.get("encryption_key_id"),
            )
            stored = self._wcp.store_ghost_copy(record, config=self._cp_config)
            return {"ghost_id": record.id, "stored": stored, "record": record.to_dict()}
        return self._call("ghost_create", op)

    def ghost_recall(self, params: dict) -> Optional[dict]:
        """Accepts either a `ghost_id` (direct fetch) or a `query` dict of
        filter fields (`system`, `type`, `time_start`, `time_end`) matched
        against the ghost index. Every candidate returned has already been
        through verify_ghost_integrity() — routes.py hands the result
        straight to warnetech_ai_controller for recall planning without
        needing to re-verify anything itself.
        """
        def op():
            ghost_id = params.get("ghost_id")
            if ghost_id:
                fetched = self._wcp.fetch_ghost_copy(ghost_id, config=self._cp_config)
                if fetched is None:
                    return None
                integrity = self._wcp.verify_ghost_integrity(ghost_id, config=self._cp_config)
                return {
                    "mode": "direct",
                    "ghost_id": ghost_id,
                    "record": fetched["record"],
                    "payload_b64": fetched["payload_b64"],
                    "integrity": integrity,
                }

            filter_params = params.get("query") or {}
            candidates = self._wcp.list_ghost_copies(filter_params, config=self._cp_config)
            verified = []
            for candidate in candidates:
                integrity = self._wcp.verify_ghost_integrity(candidate["id"], config=self._cp_config)
                verified.append({**candidate, "integrity_valid": integrity["valid"]})
            return {"mode": "query", "query": filter_params, "candidates": verified, "candidate_count": len(verified)}
        return self._call("ghost_recall", op)

    def list_ghost_copies(self, filter_params: Optional[dict] = None) -> list[dict]:
        def op():
            return self._wcp.list_ghost_copies(filter_params or {}, config=self._cp_config)
        return self._call("list_ghost_copies", op) or []

    def health(self) -> dict:
        return {"reachable": True, "mode": "in-process", "detail": self._state.snapshot()}
