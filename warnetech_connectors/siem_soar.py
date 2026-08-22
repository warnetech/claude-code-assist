"""Connectors for SIEM and SOAR systems: pushing security events out and
pulling incidents in.

push_incidents_to_control_plane writes directly to Supabase in addition to
any caller-supplied sink — every push is recorded as an ai_decisions row,
and critical/high incidents also get a security_events row.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .config import ConnectorsConfig, DEFAULT_CONFIG
from .database import insert_ai_decision, insert_security_event
from .logging import get_logger, log_error, log_push_to_control_plane, log_request, log_response
from .utils import now_iso, request_with_retry

logger = get_logger(__name__)

_DEFAULT_SOURCE = "primary_siem_soar"
_HIGH_SEVERITIES = ("critical", "high")


def push_events(events: list[dict], source: str = _DEFAULT_SOURCE, config: ConnectorsConfig = DEFAULT_CONFIG) -> dict:
    endpoint = config.find(source)
    if endpoint is None or not config.is_enabled(source):
        return {"source": source, "status": "disabled", "pushed": 0}

    log_request(logger, source, "POST", endpoint.endpoint)
    start = time.monotonic()
    headers = {"Authorization": f"Bearer {endpoint.api_key}"} if endpoint.api_key else {}
    result = request_with_retry(
        "POST", endpoint.endpoint, headers=headers, body={"events": events},
        timeout=config.timeout.read_timeout_seconds,
        max_retries=config.retry.max_retries,
        base_delay_seconds=config.retry.base_delay_seconds,
        max_delay_seconds=config.retry.max_delay_seconds,
    )
    duration_ms = (time.monotonic() - start) * 1000
    log_response(logger, source, result.ok, duration_ms, result.status)

    if not result.ok:
        log_error(logger, source, result.error or "unknown error")
        return {"source": source, "status": "error", "error": result.error, "pushed": 0}

    return {"source": source, "status": "ok", "pushed": len(events), "pushed_at": now_iso()}


def pull_incidents(query: dict, source: str = _DEFAULT_SOURCE, config: ConnectorsConfig = DEFAULT_CONFIG) -> dict:
    endpoint = config.find(source)
    if endpoint is None or not config.is_enabled(source):
        return {"source": source, "status": "disabled", "incidents": []}

    log_request(logger, source, "POST", endpoint.endpoint)
    start = time.monotonic()
    headers = {"Authorization": f"Bearer {endpoint.api_key}"} if endpoint.api_key else {}
    result = request_with_retry(
        "POST", f"{endpoint.endpoint.rstrip('/')}/incidents/query", headers=headers, body=query,
        timeout=config.timeout.read_timeout_seconds,
        max_retries=config.retry.max_retries,
        base_delay_seconds=config.retry.base_delay_seconds,
        max_delay_seconds=config.retry.max_delay_seconds,
    )
    duration_ms = (time.monotonic() - start) * 1000
    log_response(logger, source, result.ok, duration_ms, result.status)

    if not result.ok:
        log_error(logger, source, result.error or "unknown error")
        return {"source": source, "status": "error", "error": result.error, "incidents": []}

    incidents = result.body if isinstance(result.body, list) else [result.body] if result.body else []
    return {"source": source, "status": "ok", "incidents": incidents, "pulled_at": now_iso()}


def normalize_incidents(data: list[dict]) -> list[dict]:
    normalized = []
    for entry in data:
        normalized.append({
            "incident_id": entry.get("incident_id") or entry.get("id"),
            "title": entry.get("title", ""),
            "severity": entry.get("severity", "medium"),
            "status": entry.get("status", "open"),
            "created_at": entry.get("created_at", now_iso()),
            "raw": entry,
        })
    return normalized


def push_incidents_to_control_plane(data: list[dict], sink: Optional[Callable[[list[dict]], int]] = None) -> dict:
    normalized = data if data and data[0].get("incident_id") is not None and "raw" in data[0] else normalize_incidents(data)
    delivered = sink(normalized) if sink is not None else 0
    log_push_to_control_plane(logger, "siem_soar", delivered)

    insert_ai_decision("siem_soar_incident_push", {"record_count": len(normalized)}, {"records": normalized, "delivered": delivered})
    for record in normalized:
        if record.get("severity") in _HIGH_SEVERITIES:
            insert_security_event("siem_soar_incident", _DEFAULT_SOURCE, record, severity=record.get("severity", "medium"))

    return {"total": len(normalized), "delivered": delivered, "pushed_at": now_iso()}
