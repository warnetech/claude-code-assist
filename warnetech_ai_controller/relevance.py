"""Slice relevance ranking: uses embeddings and metadata to determine which
slices are needed for recall.
"""

from __future__ import annotations


from .config import AIControllerConfig, DEFAULT_CONFIG
from .utils import cosine_similarity


def rank_by_similarity(query_embedding: list[float], slice_embeddings: list[dict], config: AIControllerConfig = DEFAULT_CONFIG) -> list[dict]:
    """`slice_embeddings` is a list of dicts each carrying an `embedding`
    key alongside whatever metadata the caller wants preserved. Returns the
    same dicts annotated with `similarity`, filtered to the configured
    minimum and sorted descending.
    """
    scored = []
    for entry in slice_embeddings:
        score = cosine_similarity(query_embedding, entry.get("embedding", []))
        if score >= config.relevance.min_similarity:
            scored.append({**entry, "similarity": score})
    scored.sort(key=lambda e: e["similarity"], reverse=True)
    return scored


def rank_by_metadata(query: dict, metadata: list[dict]) -> list[dict]:
    """Scores slices by how many query fields they match exactly (domain,
    system, category) plus time-range overlap when both carry a range.
    Complements rank_by_similarity for callers with no embeddings handy —
    e.g. a CLI recall by domain/time-window alone.
    """
    scored = []
    query_keys = {k: v for k, v in query.items() if k not in ("time_start", "time_end")}

    for entry in metadata:
        score = 0.0
        matched_fields = 0
        for key, value in query_keys.items():
            if entry.get(key) == value:
                matched_fields += 1
        if query_keys:
            score += matched_fields / len(query_keys) * 0.7

        q_start, q_end = query.get("time_start"), query.get("time_end")
        e_start, e_end = entry.get("time_start"), entry.get("time_end")
        if q_start and q_end and e_start and e_end:
            overlap = not (e_end < q_start or e_start > q_end)
            if overlap:
                score += 0.3

        if score > 0:
            scored.append({**entry, "relevance": score})

    scored.sort(key=lambda e: e["relevance"], reverse=True)
    return scored
