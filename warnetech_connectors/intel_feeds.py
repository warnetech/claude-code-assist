"""Connectors for threat intelligence feeds.

`push_intel_to_control_plane` accepts an optional `sink` callable for
delivery to a control-plane buffer (e.g. warnetech_control_plane's anomaly
buffer), and — per this system's explicit wiring decision — also writes
directly to Supabase: every push is recorded as an ai_decisions row, and
records at or above the relevance threshold also get a security_events
row. This supersedes the module's original "never modifies production
data directly" design.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .config import ConnectorsConfig, DEFAULT_CONFIG
from .database import insert_ai_decision, insert_security_event
from .logging import get_logger, log_error, log_push_to_control_plane, log_request, log_response
from .utils import now_iso, request_with_retry

# Records at or above this confidence are also written to security_events,
# not just recorded as an ai_decision — matches the threshold
# warnetech_ai_controller.security_intel uses for relevance.
SECURITY_EVENT_CONFIDENCE_THRESHOLD = 0.7

logger = get_logger(__name__)


def fetch_intel_feed(source: str, config: ConnectorsConfig = DEFAULT_CONFIG) -> dict:
    endpoint = config.find(source)
    if endpoint is None or not config.is_enabled(source):
        return {"source": source, "status": "disabled", "records": []}

    log_request(logger, source, "GET", endpoint.endpoint)
    start = time.monotonic()
    headers = {"Authorization": f"Bearer {endpoint.api_key}"} if endpoint.api_key else {}
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


def normalize_intel(data: dict) -> dict:
    """Maps a raw feed record onto the common intel shape consumed by
    warnetech_ai_controller.security_intel: indicator, indicator_type,
    source, confidence, severity.
    """
    return {
        "indicator": data.get("indicator") or data.get("ioc") or data.get("value"),
        "indicator_type": data.get("indicator_type") or data.get("type", "unknown"),
        "source": data.get("source", "intel_feed"),
        "confidence": float(data.get("confidence", 0.5)),
        "severity": data.get("severity", "medium"),
        "raw": data,
        "normalized_at": now_iso(),
    }


def push_intel_to_control_plane(data: list[dict], sink: Optional[Callable[[list[dict]], int]] = None) -> dict:
    normalized = [d if d.get("normalized_at") else normalize_intel(d) for d in data]
    delivered = sink(normalized) if sink is not None else 0
    log_push_to_control_plane(logger, "intel_feeds", delivered)

    insert_ai_decision("intel_feed_push", {"record_count": len(normalized)}, {"records": normalized, "delivered": delivered})
    for record in normalized:
        if record.get("confidence", 0.0) >= SECURITY_EVENT_CONFIDENCE_THRESHOLD:
            insert_security_event("intel_feed_match", record.get("source", "intel_feed"), record, severity=record.get("severity", "medium"))

    return {"total": len(normalized), "delivered": delivered, "pushed_at": now_iso()}
