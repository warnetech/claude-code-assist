"""Main AI controller interface used by warnetech-server.

Every function here is a thin composition over the specialized modules
(embeddings, relevance, recall_planner, strategy_engine, anomaly_classifier,
test_analyzer, security_intel) — this module owns no logic of its own
beyond wiring inputs to the right submodule and shaping the combined
output. Every function returns a plain, JSON-serializable dict.

suggest_signatures, suggest_defense_strategy, classify_anomaly, and
analyze_test_results additionally persist their output to Supabase
(ai_decisions, and security_events where the result is itself
security-relevant) via database.py — a direct write, not routed through
warnetech_server, per this system's explicit wiring decision. Persistence
failures never raise; database.py fails soft, so an outage degrades to
"the analysis ran but wasn't recorded," not a broken response.
"""

from __future__ import annotations


from . import anomaly_classifier, recall_planner, relevance, security_intel, strategy_engine, test_analyzer
from .config import AIControllerConfig, DEFAULT_CONFIG
from .database import insert_ai_decision, insert_security_event
from .utils import now_iso


def rank_slices(metadata_list: list[dict], config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    """Ranks slices by importance (proportional share of total stored size)
    without requiring an external query — useful for retention/ghost-tier
    decisions where "what matters most" is a property of the slices
    themselves, not a search request.
    """
    total_size = sum(s.get("size_bytes", 0) for s in metadata_list)

    ranked = []
    for entry in metadata_list:
        size = entry.get("size_bytes", 0)
        importance = (size / total_size) if total_size else 0.0
        ranked.append({
            **entry,
            "importance": importance,
            "embedding_dims": config.embedding.dimensions,
        })
    ranked.sort(key=lambda e: e["importance"], reverse=True)

    return {
        "total_slices": len(metadata_list),
        "total_size": total_size,
        "ranked": ranked,
        "ranked_at": now_iso(),
    }


_PLAN_RECALL_HOUSEKEEPING_KEYS = ("available_slices", "total_data_size", "query_embedding")


def plan_recall(query: dict, config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    """`query` carries `available_slices` (list of slice metadata dicts,
    each optionally with an `embedding`), `total_data_size`, and either a
    `query_embedding` (for similarity ranking) or plain fields to match by
    metadata (domain, system, category, time_start/time_end).
    """
    available_slices = query.get("available_slices", [])
    query_embedding = query.get("query_embedding")
    match_fields = {k: v for k, v in query.items() if k not in _PLAN_RECALL_HOUSEKEEPING_KEYS}

    if query_embedding:
        ranked = relevance.rank_by_similarity(query_embedding, available_slices, config)
    elif match_fields:
        ranked = relevance.rank_by_metadata(match_fields, available_slices)
    else:
        # No filter signal at all: rank by size descending so plan_recall
        # still has candidates to select from, largest first.
        ranked = sorted(available_slices, key=lambda s: s.get("size_bytes", 0), reverse=True)

    plan = recall_planner.plan_recall(query, ranked, config)
    plan["recall_map"] = recall_planner.produce_recall_map(plan["slices"])
    return plan


def suggest_signatures(anomalies: list[dict], config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    recommendations = strategy_engine.suggest_signature_updates(anomalies, config)
    result = {
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "generated_at": now_iso(),
    }
    insert_ai_decision("signature_recommendation", {"anomaly_count": len(anomalies)}, result)
    return result


def suggest_defense_strategy(metrics: dict, anomalies: list[dict], config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    result = strategy_engine.suggest_defense_strategy(metrics, anomalies, intel=None, config=config)
    insert_ai_decision("defense_strategy", {"anomaly_count": len(anomalies)}, result, confidence=result.get("composite_score"))
    if result.get("posture") == "escalate":
        insert_security_event("defense_posture_escalation", "ai_controller", result, severity="high")
    return result


def classify_anomaly(event: dict) -> dict:
    result = anomaly_classifier.explain_classification(event)
    insert_security_event("anomaly_classified", "ai_controller", result, severity=event.get("severity", "medium"))
    return result


def analyze_test_results(results: list[dict]) -> dict:
    # test_analyzer.summarize_test_results persists its own ai_decisions
    # row directly — not duplicated here, same pattern as
    # integrate_external_intel relying on security_intel.py's own writes.
    return {
        "summary": test_analyzer.summarize_test_results(results),
        "failures": test_analyzer.identify_failures(results),
        "recommendations": test_analyzer.recommend_improvements(results),
    }


def integrate_external_intel(intel: list[dict], config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    merged = security_intel.merge_intel(intel)
    ranked = security_intel.rank_intel_relevance(merged, config)
    summary = security_intel.produce_intel_summary(intel)
    return {
        "summary": summary,
        "ranked_intel": ranked,
    }


_GHOST_RECALL_HOUSEKEEPING_KEYS = ("ghost_copies", "query_embedding")


def plan_recall_from_ghost(query: dict, config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    """`query` carries `ghost_copies` (the candidate list — typically
    warnetech_server's control_plane_client.list_ghost_copies() output,
    each a ghost_engine.GhostRecord dict) and optionally `query_embedding`
    for similarity ranking. Thin wrapper over recall_planner.plan_ghost_recall,
    matching plan_recall()'s shape for plain slices above.
    """
    ghost_copies = query.get("ghost_copies", [])
    query_embedding = query.get("query_embedding")
    plan = recall_planner.plan_ghost_recall(ghost_copies, query_embedding, config)
    plan["query"] = {k: v for k, v in query.items() if k not in _GHOST_RECALL_HOUSEKEEPING_KEYS}
    insert_ai_decision("ghost_recall_plan", {"ghost_copy_count": len(ghost_copies)}, plan)
    return plan


def summarize_ghost_copies(ghost_list: list[dict], config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    """Produces counts-by-system/type, total size, and time span for a set
    of ghost copies — the context /ghost/recall hands the AI controller
    alongside plan_recall_from_ghost() so a caller doesn't have to re-derive
    it from the raw list.
    """
    total_size = sum(g.get("size", 0) for g in ghost_list)
    by_system: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for g in ghost_list:
        system = g.get("system", "unknown")
        ghost_type = g.get("type", "unknown")
        by_system[system] = by_system.get(system, 0) + 1
        by_type[ghost_type] = by_type.get(ghost_type, 0) + 1

    starts = [r["start"] for g in ghost_list if (r := g.get("time_range") or {}).get("start")]
    ends = [r["end"] for g in ghost_list if (r := g.get("time_range") or {}).get("end")]

    summary = {
        "total_ghost_copies": len(ghost_list),
        "total_size": total_size,
        "by_system": by_system,
        "by_type": by_type,
        "earliest_time": min(starts) if starts else None,
        "latest_time": max(ends) if ends else None,
        "summarized_at": now_iso(),
    }
    insert_ai_decision("ghost_copy_summary", {"ghost_copy_count": len(ghost_list)}, summary)
    return summary
