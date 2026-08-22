"""Defense strategy generation, combining metrics, anomalies, test results,
and external intelligence into actionable recommendations.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from .config import AIControllerConfig, DEFAULT_CONFIG
from .utils import now_iso


def suggest_defense_strategy(metrics: dict, anomalies: list[dict], intel: Optional[list[dict]] = None, config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    intel = intel or []
    weights = config.strategy

    anomaly_severity_score = _severity_score(anomalies)
    metric_pressure_score = _metric_pressure_score(metrics)
    intel_score = min(1.0, len(intel) / 10.0)

    composite = (
        anomaly_severity_score * weights.anomaly_weight
        + metric_pressure_score * weights.metrics_weight
        + intel_score * weights.intel_weight
    )

    if composite >= 0.7:
        posture = "escalate"
    elif composite >= 0.4:
        posture = "tighten"
    else:
        posture = "maintain"

    return {
        "posture": posture,
        "composite_score": composite,
        "anomaly_severity_score": anomaly_severity_score,
        "metric_pressure_score": metric_pressure_score,
        "intel_score": intel_score,
        "anomaly_count": len(anomalies),
        "intel_count": len(intel),
        "generated_at": now_iso(),
    }


def suggest_signature_updates(anomalies: list[dict], config: AIControllerConfig = DEFAULT_CONFIG) -> list[dict]:
    """Groups anomalies by their related signature (when known) and flags
    signatures whose anomaly rate suggests they need reinforcement or
    retirement — this is a recommendation list, not a mutation; the caller
    (warnetech_control_plane's LearningEngine) applies it.
    """
    by_signature: dict[str, list[dict]] = {}
    for anomaly in anomalies:
        sig_id = anomaly.get("related_signature_id")
        if sig_id:
            by_signature.setdefault(sig_id, []).append(anomaly)

    recommendations = []
    for sig_id, group in by_signature.items():
        severities = Counter(a.get("severity", "low") for a in group)
        critical_ratio = severities.get("critical", 0) / len(group)
        recommendation = "reinforce" if critical_ratio >= config.strategy.min_confidence_for_signature_update else "monitor"
        recommendations.append({
            "signature_id": sig_id,
            "anomaly_count": len(group),
            "critical_ratio": critical_ratio,
            "recommendation": recommendation,
        })

    recommendations.sort(key=lambda r: r["critical_ratio"], reverse=True)
    return recommendations


def _severity_score(anomalies: list[dict]) -> float:
    if not anomalies:
        return 0.0
    weights = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.15}
    total = sum(weights.get(a.get("severity", "low"), 0.15) for a in anomalies)
    return min(1.0, total / (len(anomalies) * 1.0))


def _metric_pressure_score(metrics: dict) -> float:
    """Best-effort: looks for common pressure indicators without assuming
    a fixed metrics schema, since callers may pass rollups or raw samples.
    """
    indicators = []
    for key in ("error_rate", "false_positive_rate", "block_rate_delta", "cpu_percent"):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            indicators.append(min(1.0, max(0.0, value)))
    return sum(indicators) / len(indicators) if indicators else 0.0
