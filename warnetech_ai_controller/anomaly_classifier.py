"""Anomaly classification into categories: timing, header, payload,
behavioral.

Classifies by the `kind` field warnetech_control_plane's AnomalyEngine
already attaches (timing_regular, timing_burst, header_missing,
header_suspicious_ua, payload_size_outlier, payload_binary_noise,
behavioral_rate_spike) — this module maps those detector-level kinds to
the four broad categories requested here, and falls back to a best-effort
guess from the event's other fields when `kind` is absent.
"""

from __future__ import annotations

CATEGORY_PREFIXES = {
    "timing": "timing",
    "header": "header",
    "payload": "payload",
    "behavioral": "behavioral",
}


def classify(event: dict) -> str:
    kind = event.get("kind", "")
    for prefix, category in CATEGORY_PREFIXES.items():
        if kind.startswith(prefix):
            return category

    # No detector-supplied kind: infer from whatever fields are present.
    detail = event.get("detail", {})
    if "cv" in detail or "mean_ms" in detail:
        return "timing"
    if "missing" in detail or "user_agent" in detail:
        return "header"
    if "z_score" in detail or "non_printable_ratio" in detail:
        return "payload"
    if "observed_rps" in detail or "ratio" in detail:
        return "behavioral"
    return "unknown"


def explain_classification(event: dict) -> dict:
    category = classify(event)
    detail = event.get("detail", {})

    explanations = {
        "timing": "Request cadence deviated from expected regularity or burst patterns.",
        "header": "Request headers were missing expected values or looked machine-generated.",
        "payload": "Payload size or content characteristics deviated from the learned baseline.",
        "behavioral": "Observed request rate significantly exceeded the source's baseline rate.",
        "unknown": "No detector-supplied classification and no recognizable field pattern.",
    }

    return {
        "category": category,
        "explanation": explanations[category],
        "score": event.get("score"),
        "source_id": event.get("source_id"),
        "detail": detail,
    }
