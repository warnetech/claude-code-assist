"""Direct Supabase writes for warnetech_ai_controller.

Per explicit direction, controller.py, security_intel.py, and
test_analyzer.py call Supabase directly rather than routing through
warnetech_server's orchestration layer — this is the one shared, minimal
client they call into, so the urllib/PostgREST boilerplate exists once,
not three times. Every function fails soft: it logs and returns None on
any error rather than raising, since a database outage must not break the
analysis these modules primarily exist to do.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from .logging import get_logger

logger = get_logger(__name__)

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def insert_row(table: str, row: dict, timeout: float = 10.0) -> Optional[dict]:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        logger.warning("supabase not configured; insert skipped", table=table)
        return None

    url = f"{_SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
    data = json.dumps(row, default=str).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", _SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {_SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=representation")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            result = json.loads(raw) if raw else None
            row_result = result[0] if result else None
            logger.info("row inserted", table=table, ok=row_result is not None)
            return row_result
    except urllib.error.HTTPError as exc:
        logger.error("insert failed", table=table, status=exc.code, body=exc.read().decode(errors="replace"))
        return None
    except urllib.error.URLError as exc:
        logger.error("supabase unreachable", table=table, reason=str(exc.reason))
        return None


def insert_ai_decision(decision_type: str, input_data: dict, output_data: dict, confidence: Optional[float] = None) -> Optional[dict]:
    return insert_row("ai_decisions", {
        "decision_type": decision_type,
        "input": input_data,
        "output": output_data,
        "confidence": confidence,
    })


def insert_security_event(event_type: str, source: str, details: dict, severity: str = "medium") -> Optional[dict]:
    """Signature unchanged (event_type, source, details, severity) so every
    call site in controller.py and security_intel.py needs no changes —
    but the row written now matches security_events' ACTUAL live columns
    (id, event_type, severity, detail), verified directly against
    tewartech-project-supabase. There is no standalone `source`/`details`
    column live; `source` and `details` are nested under `detail` instead
    of flattened together, so a details dict that happens to carry its own
    "source" key can never collide with the caller's `source` argument.
    """
    return insert_row("security_events", {
        "event_type": event_type,
        "severity": severity,
        "detail": {"source": source, "payload": details},
    })


def insert_test_result(scenario: str, status: str, details: dict, metrics: Optional[dict] = None, anomalies: Optional[dict] = None) -> Optional[dict]:
    return insert_row("test_results", {
        "scenario": scenario,
        "status": status,
        "details": details,
        "metrics": metrics or {},
        "anomalies": anomalies or {},
    })
