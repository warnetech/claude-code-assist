"""Analysis of containerised test harness results: summarization, failure
identification, and improvement recommendations.

Consumes the shape warnetech_server's TestResult.to_dict() produces
(test_id, scenario_name, kind, payload_count, success_count, failure_count,
mean_duration_ms, success_rate, logs) — but only reads keys it needs, so it
tolerates extra fields or a slightly different result shape from other
callers.

summarize_test_results persists its output directly to Supabase's
ai_decisions table, per this system's explicit decision to wire
persistence into this layer rather than route it through warnetech_server.
"""

from __future__ import annotations

import statistics

from .database import insert_ai_decision
from .utils import now_iso


def summarize_test_results(results: list[dict]) -> dict:
    if not results:
        summary = {"total_tests": 0, "summarized_at": now_iso()}
        insert_ai_decision("test_result_summary", {"result_count": 0}, summary)
        return summary

    success_rates = [r.get("success_rate", 0.0) for r in results]
    durations = [r.get("mean_duration_ms", 0.0) for r in results]
    by_kind: dict[str, int] = {}
    for r in results:
        kind = r.get("kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1

    summary = {
        "total_tests": len(results),
        "by_kind": by_kind,
        "mean_success_rate": statistics.fmean(success_rates),
        "worst_success_rate": min(success_rates),
        "mean_duration_ms": statistics.fmean(durations) if durations else 0.0,
        "summarized_at": now_iso(),
    }
    insert_ai_decision("test_result_summary", {"result_count": len(results)}, summary, confidence=summary["mean_success_rate"])
    return summary


def identify_failures(results: list[dict], failure_threshold: float = 0.8) -> list[dict]:
    """Flags any result whose success rate is below `failure_threshold`,
    ranked worst-first.
    """
    failures = [
        {
            "test_id": r.get("test_id"),
            "scenario_name": r.get("scenario_name"),
            "kind": r.get("kind"),
            "success_rate": r.get("success_rate", 0.0),
            "failure_count": r.get("failure_count", 0),
        }
        for r in results
        if r.get("success_rate", 1.0) < failure_threshold
    ]
    failures.sort(key=lambda f: f["success_rate"])
    return failures


def recommend_improvements(results: list[dict]) -> list[dict]:
    recommendations = []
    failures = identify_failures(results)

    for failure in failures:
        if failure["success_rate"] < 0.5:
            action = "review_scenario"
            reason = "less than half of payloads succeeded — the scenario or its container profile may be misconfigured"
        else:
            action = "reinforce_signatures"
            reason = "some payloads bypassed detection — candidate for signature reinforcement"

        recommendations.append({
            "test_id": failure["test_id"],
            "scenario_name": failure["scenario_name"],
            "action": action,
            "reason": reason,
        })

    return recommendations
