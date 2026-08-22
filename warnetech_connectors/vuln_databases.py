"""Connectors for vulnerability databases (e.g. NVD).

push_vuln_to_control_plane writes directly to Supabase in addition to any
caller-supplied sink — every push is recorded as an ai_decisions row, and
high-severity vulnerabilities also get a security_events row.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .config import ConnectorsConfig, DEFAULT_CONFIG
from .database import insert_ai_decision, insert_security_event
from .logging import get_logger, log_error, log_push_to_control_plane, log_request, log_response
from .utils import now_iso, request_with_retry

logger = get_logger(__name__)

_HIGH_SEVERITIES = ("critical", "high")


def fetch_vuln_data(source: str, config: ConnectorsConfig = DEFAULT_CONFIG) -> dict:
    endpoint = config.find(source)
    if endpoint is None or not config.is_enabled(source):
        return {"source": source, "status": "disabled", "records": []}

    log_request(logger, source, "GET", endpoint.endpoint)
    start = time.monotonic()
    headers = {"apiKey": endpoint.api_key} if endpoint.api_key else {}
    result = request_with_retry(
        "GET", endpoint.endpoint, headers=headers,
        timeout=config.timeout.read_timeout_seconds,
        max_retries=config.retry.max_retries,
        base_delay_seconds=config.retry.base_delay_seconds,
        max_delay_seconds=config.retry.max_delay_seconds,
    )
    duration_ms = (time.monotonic() - start) * 1000
    log_response(logger, source, result.ok, duration_ms, result.status)

    if not result.ok:
        log_error(logger, source, result.error or "unknown error")
        return {"source": source, "status": "error", "error": result.error, "records": []}

    records = result.body if isinstance(result.body, list) else [result.body] if result.body else []
    return {"source": source, "status": "ok", "records": records, "fetched_at": now_iso()}


def normalize_vuln(data: dict) -> dict:
    return {
        "indicator": data.get("cve_id") or data.get("id"),
        "indicator_type": "cve",
        "source": data.get("source", "vuln_database"),
        "confidence": float(data.get("confidence", 0.8)),
        "severity": data.get("severity", data.get("cvss_severity", "medium")),
        "raw": data,
        "normalized_at": now_iso(),
    }


def push_vuln_to_control_plane(data: list[dict], sink: Optional[Callable[[list[dict]], int]] = None) -> dict:
    normalized = [d if d.get("normalized_at") else normalize_vuln(d) for d in data]
    delivered = sink(normalized) if sink is not None else 0
    log_push_to_control_plane(logger, "vuln_databases", delivered)

    insert_ai_decision("vuln_push", {"record_count": len(normalized)}, {"records": normalized, "delivered": delivered})
    for record in normalized:
        if record.get("severity") in _HIGH_SEVERITIES:
            insert_security_event("vulnerability_detected", record.get("source", "vuln_database"), record, severity=record.get("severity", "medium"))

    return {"total": len(normalized), "delivered": delivered, "pushed_at": now_iso()}
