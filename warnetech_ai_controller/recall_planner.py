"""Reconstruction planning: given a query, determines the minimal set of
slices (or ghost copies) needed to satisfy it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

from .config import AIControllerConfig, DEFAULT_CONFIG
from .utils import cosine_similarity, now_iso


def plan_recall(query: dict, ranked_slices: list[dict], config: AIControllerConfig = DEFAULT_CONFIG) -> dict:
    """Greedily accepts slices in rank order (already sorted by the caller,
    typically via relevance.rank_by_similarity or rank_by_metadata) until
    either the configured coverage ratio of `query['total_data_size']` is
    reached or `recall.max_slices` is hit — whichever comes first.
    """
    total_size = query.get("total_data_size", 0)
    target_size = int(total_size * config.recall.target_coverage_ratio) if total_size else None

    selected: list[dict] = []
    accumulated = 0
    for entry in ranked_slices:
        if len(selected) >= config.recall.max_slices:
            break
        if target_size is not None and accumulated >= target_size:
            break
        selected.append(entry)
        accumulated += entry.get("size_bytes", 0)

    coverage_ratio = (accumulated / total_size) if total_size else None

    return {
        "query": query,
        "selected_slice_count": len(selected),
        "selected_data_size": accumulated,
        "total_data_size": total_size,
        "coverage_ratio": coverage_ratio,
        "meets_target": coverage_ratio is None or coverage_ratio <= config.recall.target_coverage_ratio,
        "slices": selected,
        "planned_at": now_iso(),
    }


def produce_recall_map(slices: list[dict]) -> dict:
    """Builds an ordered reconstruction map — the sequence and locations a
    caller should fetch/decrypt/decompress slices in. Time-ordered when
    every slice carries a `time_start`, otherwise preserves input order.
    """
    orderable = all("time_start" in s for s in slices)
    ordered = sorted(slices, key=lambda s: s["time_start"]) if orderable else list(slices)

    return {
        "order": "time" if orderable else "input",
        "steps": [
            {
                "sequence": i,
                "slice_id": s.get("slice_id"),
                "path": s.get("path"),
                "domain": s.get("domain"),
            }
            for i, s in enumerate(ordered)
        ],
        "total_steps": len(ordered),
    }


# ---------------------------------------------------------------------------
# Ghost copy recall planning
#
# Ghost copies (warnetech_control_plane.ghost_engine.GhostRecord dicts) have
# a different shape from slice metadata: no `size_bytes`, no `embedding` at
# the top level (it lives under `metadata["embedding"]`, set by
# ghost_engine.create_ghost_copy at write time), and `time_range` instead of
# `time_start`/`time_end`. Kept separate from plan_recall/produce_recall_map
# above rather than overloading them with branching on shape.
# ---------------------------------------------------------------------------


def _matches_ghost_metadata_filters(
    copy: dict, system: Optional[str], type_: Optional[str], time_start: Optional[str], time_end: Optional[str],
) -> bool:
    """True only if `copy` satisfies every supplied filter (AND semantics)
    — an unsupplied filter never restricts. time_range uses an overlap
    test, not an exact match, since a single query window commonly spans
    several ghost copies' ranges; that overlap is what makes a multi-ghost
    reconstruction plan possible in the first place.
    """
    if system is not None and copy.get("system") != system:
        return False

    if type_ is not None and copy.get("type") != type_:
        return False

    if time_start is not None and time_end is not None:
        r = copy.get("time_range") or {}
        r_start, r_end = r.get("start"), r.get("end")
        if not r_start or not r_end or r_end < time_start or r_start > time_end:
            return False

    return True


def plan_ghost_recall(
    ghost_copies: list[dict],
    query_embedding: Optional[list[float]] = None,
    config: AIControllerConfig = DEFAULT_CONFIG,
    system: Optional[str] = None,
    type_: Optional[str] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
) -> dict:
    """Determines the set of ghost copies needed to satisfy a recall
    request — potentially several, for reconstructing a query that spans
    more than one ghost copy's time_range (a multi-ghost reconstruction
    plan), not just a single best match.

    `system`/`type_`/`time_start`+`time_end` are optional metadata filters
    (AND semantics — see _matches_ghost_metadata_filters): when any is
    supplied, candidates are narrowed to matches before ranking. This lets
    a caller select an entire time window's worth of ghost copies for one
    system/type without needing an embedding at all.

    Within the (possibly filtered) candidate set: with a `query_embedding`,
    ranks by cosine similarity against each copy's `metadata["embedding"]`
    (set by ghost_engine at creation), keeping only those above
    `config.relevance.min_similarity`. Without one, metadata-filtered
    candidates are ordered chronologically by time_range (a natural
    reconstruction sequence); with no filters and no embedding, behavior
    is unchanged from before this function had metadata awareness:
    newest-first, since a ghost copy carries no `size_bytes` to rank by
    like a plain slice. Either way the result is capped at
    `config.recall.max_slices`.
    """
    metadata_filters_given = system is not None or type_ is not None or (time_start is not None and time_end is not None)

    candidates = ghost_copies
    if metadata_filters_given:
        candidates = [c for c in candidates if _matches_ghost_metadata_filters(c, system, type_, time_start, time_end)]

    if query_embedding:
        scored = []
        for copy in candidates:
            embedding = (copy.get("metadata") or {}).get("embedding", [])
            score = cosine_similarity(query_embedding, embedding) if embedding else 0.0
            if score >= config.relevance.min_similarity:
                scored.append({**copy, "similarity": score})
        scored.sort(key=lambda c: c["similarity"], reverse=True)
        ranked = scored
    elif metadata_filters_given:
        ranked = sorted(candidates, key=lambda c: (c.get("time_range") or {}).get("start") or c.get("created_at", ""))
    else:
        ranked = sorted(candidates, key=lambda c: c.get("created_at", ""), reverse=True)

    selected = ranked[: config.recall.max_slices]
    total_size = sum(c.get("size", 0) for c in selected)

    return {
        "selected_ghost_count": len(selected),
        "selected_total_size": total_size,
        "ghost_copies": selected,
        "recall_map": produce_ghost_recall_map(selected),
        "planned_at": now_iso(),
    }


def produce_ghost_recall_map(ghost_copies: list[dict]) -> dict:
    """Builds an ordered, control-plane-executable recall plan: one fetch
    step per ghost copy, oldest `time_range` first when every copy carries
    one, otherwise input order. Each step's `ghost_id` is what a caller
    passes to ghost_engine.fetch_ghost_copy() to actually pull the payload.
    """
    orderable = all((c.get("time_range") or {}).get("start") for c in ghost_copies)
    ordered = sorted(ghost_copies, key=lambda c: c["time_range"]["start"]) if orderable else list(ghost_copies)

    return {
        "order": "time" if orderable else "input",
        "steps": [
            {
                "sequence": i,
                "ghost_id": c.get("id"),
                "system": c.get("system"),
                "type": c.get("type"),
            }
            for i, c in enumerate(ordered)
        ],
        "total_steps": len(ordered),
    }


# ---------------------------------------------------------------------------
# Ghost relevance scoring + reconstruction plan object
#
# Purely additive on top of plan_ghost_recall()/produce_ghost_recall_map()
# above — no existing function's signature changes. Where plan_ghost_recall()
# filters candidates by exact system/type match and time_range overlap,
# score_ghost_relevance() instead produces a continuous [0, 1] relevance
# score per candidate (time proximity + system match + type match), and
# build_reconstruction_plan() uses that score to assemble a multi-ghost
# ReconstructionPlan: every candidate worth using to rebuild a state
# window, not just an exact-match subset.
# ---------------------------------------------------------------------------

_RECONSTRUCTION_SYSTEM_MATCH_WEIGHT = 0.35
_RECONSTRUCTION_TYPE_MATCH_WEIGHT = 0.35
_RECONSTRUCTION_TIME_PROXIMITY_WEIGHT = 0.30
_RECONSTRUCTION_TIME_OVERLAP_WEIGHT = 0.30

# How far (in seconds) past the nearest edge of a ghost copy's time_range
# its time-proximity score decays to zero. One week is generous enough
# that ghost copies adjacent to the query window still contribute to a
# reconstruction plan, not just ones that contain it exactly.
_TIME_PROXIMITY_DECAY_SECONDS = 7 * 86400


def _parse_iso_epoch(timestamp: Optional[str]) -> Optional[float]:
    """Parses an ISO-8601 timestamp (with or without a trailing 'Z') to
    epoch seconds. Returns None for missing/unparseable input rather than
    raising — relevance scoring must never crash a recall request over a
    malformed timestamp.
    """
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _time_proximity_score(ghost_copy: dict, query_time_epoch: Optional[float]) -> Optional[float]:
    """1.0 when query_time falls inside the copy's time_range, decaying
    linearly to 0.0 at _TIME_PROXIMITY_DECAY_SECONDS past the nearer edge.
    Returns None (not 0.0) when there's nothing to compare — an
    unparseable/missing time_range or no query_time — so the caller can
    tell "no signal" apart from "far away" and exclude it from scoring
    rather than penalizing it.
    """
    if query_time_epoch is None:
        return None
    time_range = ghost_copy.get("time_range") or {}
    start_epoch = _parse_iso_epoch(time_range.get("start"))
    end_epoch = _parse_iso_epoch(time_range.get("end"))
    if start_epoch is None or end_epoch is None:
        return None
    if start_epoch <= query_time_epoch <= end_epoch:
        return 1.0
    distance = start_epoch - query_time_epoch if query_time_epoch < start_epoch else query_time_epoch - end_epoch
    return max(0.0, 1.0 - distance / _TIME_PROXIMITY_DECAY_SECONDS)


def _time_window_overlap_score(
    ghost_copy: dict, window_start_epoch: Optional[float], window_end_epoch: Optional[float],
) -> Optional[float]:
    """Normalized [0, 1] overlap between the copy's time_range and a
    requested recall window, as intersection-duration / union-duration (a
    Jaccard-style ratio): 1.0 when the two ranges are identical, 0.0 when
    they don't overlap at all, and something in between otherwise —
    unlike _time_proximity_score's single-point decay, this rewards a
    ghost copy for how much of the *whole requested window* it actually
    covers. Returns None (not 0.0), matching _time_proximity_score's
    convention, when there's nothing to compare: a missing/unparseable
    window or time_range, or an inverted range on either side.
    """
    if window_start_epoch is None or window_end_epoch is None or window_end_epoch < window_start_epoch:
        return None
    time_range = ghost_copy.get("time_range") or {}
    start_epoch = _parse_iso_epoch(time_range.get("start"))
    end_epoch = _parse_iso_epoch(time_range.get("end"))
    if start_epoch is None or end_epoch is None or end_epoch < start_epoch:
        return None

    intersection = max(0.0, min(end_epoch, window_end_epoch) - max(start_epoch, window_start_epoch))
    union = max(end_epoch, window_end_epoch) - min(start_epoch, window_start_epoch)

    if union <= 0.0:
        # Both ranges collapse to the same zero-duration instant.
        return 1.0 if start_epoch == window_start_epoch else 0.0

    return intersection / union


def score_ghost_relevance(
    ghost_copy: dict,
    system: Optional[str] = None,
    type_: Optional[str] = None,
    query_time: Optional[str] = None,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> float:
    """Continuous relevance score in [0, 1] for one ghost copy, combining
    system match, type match, single-point time proximity, and — when a
    requested recall window is supplied — how much of that window the
    copy's time_range actually overlaps. Independent of embeddings, so it
    works for callers with no query_embedding at all.

    `window_start`/`window_end` are new, optional, and additive: existing
    callers that only pass `query_time` (or nothing) see no change in
    behavior — _time_window_overlap_score() returns None when the window
    is absent, exactly like the other cues, so it's simply excluded from
    the weighted average below rather than contributing a 0.

    Any cue left unsupplied (None) is excluded from the weighted average
    and the remaining weights renormalize, so a partial query (e.g. system
    only) still produces a meaningful score instead of being penalized for
    the cues it didn't supply. Supplying nothing scores every candidate 0.0.
    """
    query_time_epoch = _parse_iso_epoch(query_time)
    window_start_epoch = _parse_iso_epoch(window_start)
    window_end_epoch = _parse_iso_epoch(window_end)
    weighted_components: list[tuple[float, float]] = []

    if system is not None:
        weighted_components.append((_RECONSTRUCTION_SYSTEM_MATCH_WEIGHT, 1.0 if ghost_copy.get("system") == system else 0.0))

    if type_ is not None:
        weighted_components.append((_RECONSTRUCTION_TYPE_MATCH_WEIGHT, 1.0 if ghost_copy.get("type") == type_ else 0.0))

    proximity = _time_proximity_score(ghost_copy, query_time_epoch)
    if proximity is not None:
        weighted_components.append((_RECONSTRUCTION_TIME_PROXIMITY_WEIGHT, proximity))

    overlap = _time_window_overlap_score(ghost_copy, window_start_epoch, window_end_epoch)
    if overlap is not None:
        weighted_components.append((_RECONSTRUCTION_TIME_OVERLAP_WEIGHT, overlap))

    if not weighted_components:
        return 0.0

    total_weight = sum(weight for weight, _ in weighted_components)
    return sum(weight * score for weight, score in weighted_components) / total_weight


@dataclass(frozen=True)
class ReconstructionStep:
    sequence: int
    ghost_id: Optional[str]
    system: Optional[str]
    type: Optional[str]
    relevance_score: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReconstructionPlan:
    """The reconstruction-plan object: which ghost copies to use and in
    what order to rebuild a state window, distinct from
    produce_ghost_recall_map()'s dict-shaped output above (kept as-is for
    plan_ghost_recall() callers) so this new capability never has to
    change that existing return shape.
    """

    steps: list[ReconstructionStep] = field(default_factory=list)
    order: str = "relevance"
    planned_at: str = field(default_factory=now_iso)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "order": self.order,
            "total_steps": self.total_steps,
            "planned_at": self.planned_at,
        }


def build_reconstruction_plan(
    ghost_copies: list[dict],
    system: Optional[str] = None,
    type_: Optional[str] = None,
    query_time: Optional[str] = None,
    order: str = "relevance",
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> ReconstructionPlan:
    """Builds a multi-ghost ReconstructionPlan: every candidate that scores
    above 0.0 via score_ghost_relevance() becomes a step, not just a single
    best match, so a query spanning a state window wider than any one
    ghost copy still gets every copy it needs back in one plan.

    `order` picks the step sequence: "relevance" (highest score first, the
    default) or "time" (chronological by time_range.start, for a plan
    meant to be replayed in wall-clock order during reconstruction).

    `window_start`/`window_end` are new, optional, and additive — forwarded
    straight through to score_ghost_relevance()'s own window overlap
    scoring. Existing callers that omit them see no change: both default
    to None, exactly as score_ghost_relevance() itself already expects.
    """
    scored = [
        (copy, score_ghost_relevance(
            copy, system=system, type_=type_, query_time=query_time,
            window_start=window_start, window_end=window_end,
        ))
        for copy in ghost_copies
    ]
    scored = [(copy, score) for copy, score in scored if score > 0.0]

    if order == "time":
        scored.sort(key=lambda pair: (pair[0].get("time_range") or {}).get("start") or "")
    else:
        scored.sort(key=lambda pair: pair[1], reverse=True)

    steps = [
        ReconstructionStep(
            sequence=i,
            ghost_id=copy.get("id"),
            system=copy.get("system"),
            type=copy.get("type"),
            relevance_score=score,
        )
        for i, (copy, score) in enumerate(scored)
    ]

    return ReconstructionPlan(steps=steps, order=order, planned_at=now_iso())
