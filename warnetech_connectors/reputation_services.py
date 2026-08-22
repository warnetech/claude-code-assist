"""Connectors for IP/domain/URL reputation services (Malwarebytes, Norton,
McAfee).

push_reputation_to_control_plane writes directly to Supabase in addition
to any caller-supplied sink — every push is recorded as an ai_decisions
row, and high-confidence verdicts also get a security_events row.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .config import ConnectorsConfig, DEFAULT_CONFIG
from .database import insert_ai_decision, insert_security_event
from .logging import get_logger, log_error, log_push_to_control_plane, log_request, log_response
from .utils import now_iso, request_with_retry

logger = get_logger(__name__)

SECURITY_EVENT_CONFIDENCE_THRESHOLD = 0.7


def query_reputation(target: str, source: str = "malwarebytes", config: ConnectorsConfig = DEFAULT_CONFIG) -> dict:
    endpoint = config.find(source)
    if endpoint is None or not config.is_enabled(source):
        return {"source": source, "target": target, "status": "disabled"}

    log_request(logger, source, "GET", endpoint.endpoint)
    start = time.monotonic()
    headers = {"Authorization": f"Bearer {endpoint.api_key}"} if endpoint.api_key else {}
    result = request_with_retry(
        "GET", f"{endpoint.endpoint.rstrip('/')}?target={target}", headers=headers,
        timeout=config.timeout.read_timeout_seconds,
        max_retries=config.retry.max_retries,
        base_delay_seconds=config.retry.base_delay_seconds,
        max_delay_seconds=config.retry.max_delay_seconds,
    )
    duration_ms = (time.monotonic() - start) * 1000
    log_response(logger, source, result.ok, duration_ms, result.status)

    if not result.ok:
        log_error(logger, source, result.error or "unknown error")
        return {"source": source, "target": target, "status": "error", "error": result.error}

    return {"source": source, "target": target, "status": "ok", "verdict": result.body, "queried_at": now_iso()}


def normalize_reputation(data: dict) -> dict:
    verdict = data.get("verdict") or {}
    return {
        "indicator": data.get("target"),
        "indicator_type": verdict.get("type", "url") if isinstance(verdict, dict) else "url",
        "source": data.get("source", "reputation_service"),
        "confidence": float(verdict.get("confidence", 0.5)) if isinstance(verdict, dict) else 0.5,
        "severity": verdict.get("severity", "medium") if isinstance(verdict, dict) else "medium",
        "raw": data,
        "normalized_at": now_iso(),
    }


def push_reputation_to_control_plane(data: list[dict], sink: Optional[Callable[[list[dict]], int]] = None) -> dict:
    normalized = [d if d.get("normalized_at") else normalize_reputation(d) for d in data]
    delivered = sink(normalized) if sink is not None else 0
    log_push_to_control_plane(logger, "reputation_services", delivered)

    insert_ai_decision("reputation_push", {"record_count": len(normalized)}, {"records": normalized, "delivered": delivered})
    for record in normalized:
        if record.get("confidence", 0.0) >= SECURITY_EVENT_CONFIDENCE_THRESHOLD:
            insert_security_event("reputation_match", record.get("source", "reputation_service"), record, severity=record.get("severity", "medium"))

    return {"total": len(normalized), "delivered": delivered, "pushed_at": now_iso()}
