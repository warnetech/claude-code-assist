"""Interactions with warnetech-project-supabase: reading/writing metrics,
storing test results, persisting AI decisions, logging security events, and
managing partitions/rollups.

Uses only the standard library (`urllib`), same pattern as
warnetech_control_plane/database.py. Every method fails soft — logs and
returns None/False rather than raising — because a database outage must
never take the API layer down with it; routes.py degrades individual
responses instead of 500ing the whole request.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

from .config import ServerConfig
from .logging import get_logger, log_database_operation

logger = get_logger(__name__)


class ServerDatabase:
    def __init__(self, config: ServerConfig) -> None:
        self._config = config

    @property
    def _available(self) -> bool:
        return bool(self._config.database.supabase_url and self._config.database.supabase_key)

    def _request(self, method: str, path: str, body: Optional[Any] = None, params: Optional[dict] = None) -> Any:
        if not self._available:
            logger.warning("database not configured; request skipped", path=path)
            return None

        url = f"{self._config.database.supabase_url.rstrip('/')}/rest/v1/{path.lstrip('/')}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"

        data = json.dumps(body, default=str).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("apikey", self._config.database.supabase_key)
        req.add_header("Authorization", f"Bearer {self._config.database.supabase_key}")
        req.add_header("Content-Type", "application/json")
        if method in ("POST", "PATCH"):
            req.add_header("Prefer", "return=representation")

        try:
            with urllib.request.urlopen(req, timeout=self._config.database.request_timeout_seconds) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            logger.error("database http error", path=path, status=exc.code, body=exc.read().decode(errors="replace"))
            return None
        except urllib.error.URLError as exc:
            logger.error("database unreachable", path=path, reason=str(exc.reason))
            return None

    # -- metrics --------------------------------------------------------------

    def read_metrics(self, source_id: str, limit: int = 500) -> list[dict]:
        result = self._request("GET", "metric_rollups", params={"select": "*", "source_id": f"eq.{source_id}", "limit": limit})
        return result or []

    def write_metrics(self, rollups: list[dict]) -> bool:
        if not rollups:
            return True
        ok = self._request("POST", "metric_rollups", body=rollups) is not None
        log_database_operation(logger, "write", "metric_rollups", ok)
        return ok

    # -- test results -----------------------------------------------------------

    def store_test_result(self, result: dict) -> Optional[dict]:
        response = self._request("POST", "test_results", body=[result])
        log_database_operation(logger, "write", "test_results", response is not None)
        return response[0] if response else None

    def read_test_results(self, test_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        params = {"select": "*", "limit": limit}
        if test_id:
            params["id"] = f"eq.{test_id}"
        result = self._request("GET", "test_results", params=params)
        return result or []

    # -- AI decisions ---------------------------------------------------------------

    def persist_ai_decision(self, decision: dict) -> Optional[dict]:
        response = self._request("POST", "ai_decisions", body=[decision])
        log_database_operation(logger, "write", "ai_decisions", response is not None)
        return response[0] if response else None

    # -- security events --------------------------------------------------------------

    def log_security_event(self, event: dict) -> bool:
        """Accepts the conventional (event_type, source, details, severity)
        shape callers already build — log_ghost_creation/log_ghost_recall
        below need no changes — but maps it onto security_events' ACTUAL
        live columns (id, event_type, severity, detail), verified directly
        against tewartech-project-supabase. There is no standalone
        `source`/`details` column live; both are nested under `detail`
        instead of flattened, so a details dict with its own "source" key
        can never collide with the caller's `source`.
        """
        row = {
            "event_type": event.get("event_type"),
            "severity": event.get("severity", "medium"),
            "detail": {"source": event.get("source"), "payload": event.get("details") or {}},
        }
        ok = self._request("POST", "security_events", body=[row]) is not None
        log_database_operation(logger, "write", "security_events", ok)
        return ok

    # -- partitions / rollups (RPC) -------------------------------------------------------

    def call_rpc(self, function_name: str, args: dict) -> Any:
        return self._request("POST", f"rpc/{function_name}", body=args)

    def sync_partitions(self) -> bool:
        ok = self.call_rpc("maintain_partitions", {}) is not None
        log_database_operation(logger, "rpc", "maintain_partitions", ok)
        return ok

    def sync_threat_event_partitions(self) -> bool:
        """Dedicated threat_events partition maintenance — redundant with
        (not a replacement for) sync_partitions()'s own threat_events
        coverage; both are idempotent, so calling both is harmless.
        """
        ok = self.call_rpc("maintain_threat_event_partitions", {}) is not None
        log_database_operation(logger, "rpc", "maintain_threat_event_partitions", ok)
        return ok

    def refresh_rollups(self) -> bool:
        ok = self.call_rpc("refresh_metric_rollups", {}) is not None
        log_database_operation(logger, "rpc", "refresh_metric_rollups", ok)
        return ok

    def health(self) -> dict:
        return {"configured": self._available}

    # -- ghost copies -----------------------------------------------------------------
    #
    # No dedicated ghost_log table exists in supabase_schema/tables.sql, so
    # per explicit direction these route to security_events (operational
    # events) and ai_decisions (recall-planning output) instead of a new table.

    def log_ghost_creation(self, ghost_result: dict) -> bool:
        record = ghost_result.get("record", {}) if ghost_result else {}
        return self.log_security_event({
            "event_type": "ghost_copy_created",
            "source": "warnetech_server",
            "details": {
                "ghost_id": (ghost_result or {}).get("ghost_id"),
                "system": record.get("system"),
                "type": record.get("type"),
                "size": record.get("size"),
            },
            "severity": "low",
        })

    def log_ghost_recall(self, query: dict, fetch_result: dict, plan: Optional[dict] = None) -> bool:
        """Built directly in the live {event_type, severity, detail} shape
        (same pattern as log_retention_ghost_creation in
        warnetech_control_plane/database.py) rather than through
        log_security_event()'s legacy (event_type, source, details,
        severity) wrapper — `detail` here IS the jsonb payload, no further
        remapping needed.
        """
        fetch_result = fetch_result or {}
        row = {
            "event_type": "ghost_copy_recalled",
            "severity": "low",
            "detail": {
                "source": "warnetech_server",
                "mode": fetch_result.get("mode"),
                "ghost_id": fetch_result.get("ghost_id"),
                "candidate_count": fetch_result.get("candidate_count"),
                "selected_ghost_count": (plan or {}).get("selected_ghost_count"),
            },
        }
        ok = self._request("POST", "security_events", body=[row]) is not None
        log_database_operation(logger, "write", "security_events", ok)
        return ok

    def store_ghost_metrics(self, metrics: dict) -> Optional[dict]:
        return self.persist_ai_decision({
            "decision_type": "ghost_metrics",
            "input": {},
            "output": metrics,
            "confidence": None,
        })
