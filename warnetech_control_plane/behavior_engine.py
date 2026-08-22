"""Behavioral analysis: request-rate analysis, pattern detection, and source
reputation scoring.

Feeds `behavioral_score` into scoring_engine.ScoringEngine.score(). Kept
free of any external I/O so it can run on the hot path alongside
signature_engine.match().
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Iterable, Sequence

from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .logging import get_logger

logger = get_logger(__name__)


class BehaviorEngine:
    def __init__(self, config: ControlPlaneConfig = DEFAULT_CONFIG) -> None:
        self._config = config

    # -- rate analysis --------------------------------------------------------

    def rate_analysis(self, request_count: int, window_seconds: float, baseline_rps: float) -> float:
        """Returns a 0-1 score for how far the observed rate exceeds baseline."""
        if window_seconds <= 0 or baseline_rps <= 0:
            return 0.0
        observed_rps = request_count / window_seconds
        ratio = observed_rps / baseline_rps
        if ratio <= 1.0:
            return 0.0
        # Saturates at 1.0 once traffic is 10x baseline.
        return min(1.0, (ratio - 1.0) / 9.0)

    # -- pattern detection ------------------------------------------------------

    def pattern_detection(self, sequence: Sequence[str]) -> float:
        """Scores how repetitive/scripted a sequence of endpoints or actions
        looks. High repetition of a short cycle (e.g. probing the same three
        paths on loop) scores near 1.0; varied human-like sequences near 0.
        """
        if len(sequence) < 4:
            return 0.0

        counts = Counter(sequence)
        most_common_count = counts.most_common(1)[0][1]
        repetition_ratio = most_common_count / len(sequence)

        # Detect short repeating cycles (period 2-5).
        cycle_score = 0.0
        for period in range(2, min(6, len(sequence) // 2 + 1)):
            windows = [tuple(sequence[i : i + period]) for i in range(0, len(sequence) - period, period)]
            if len(windows) >= 2 and len(set(windows)) == 1:
                cycle_score = max(cycle_score, 0.7)

        return min(1.0, max(repetition_ratio, cycle_score))

    # -- reputation ---------------------------------------------------------------

    def source_reputation(self, true_positive_count: int, false_positive_count: int, total_events: int) -> float:
        """Returns 0 (trusted) to 1 (untrusted) based on this source's
        historical outcomes. Unknown sources (no history) default to 0.3 —
        cautious but not blocked.
        """
        if total_events <= 0:
            return 0.3
        bad_ratio = true_positive_count / total_events
        # Sources that repeatedly false-positive are noisy, not malicious —
        # dampen their contribution rather than penalizing them like a TP.
        noise_penalty = min(0.2, false_positive_count / max(1, total_events) * 0.2)
        return max(0.0, min(1.0, bad_ratio - noise_penalty))

    def mean_confidence(self, scores: Iterable[float]) -> float:
        scores = list(scores)
        return statistics.fmean(scores) if scores else 0.0
