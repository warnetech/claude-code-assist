"""Anomaly detection: timing, header, payload, and behavioral anomalies.

Each detector returns zero or more anomaly dicts with a `score` in [0, 1]
and a `kind` describing which detector fired, so scoring_engine can combine
them without needing to know detector internals.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional

from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .logging import get_logger
from .utils import now_iso

logger = get_logger(__name__)


@dataclass
class Anomaly:
    kind: str
    source_id: str
    score: float
    detail: dict = field(default_factory=dict)
    detected_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


class AnomalyEngine:
    def __init__(self, config: ControlPlaneConfig = DEFAULT_CONFIG) -> None:
        self._config = config

    # -- timing ---------------------------------------------------------------

    def detect_timing_anomaly(self, source_id: str, intervals_ms: list[float]) -> Optional[Anomaly]:
        """Flags request cadence that is either too regular (bot-like) or
        has a sudden burst relative to its own recent history.
        """
        if len(intervals_ms) < 5:
            return None

        mean = statistics.fmean(intervals_ms)
        stdev = statistics.pstdev(intervals_ms) if len(intervals_ms) > 1 else 0.0
        coefficient_of_variation = (stdev / mean) if mean else 0.0

        # Very low CoV => machine-regular cadence. Very high CoV with a low
        # mean => bursty flooding.
        if coefficient_of_variation < 0.05:
            return Anomaly("timing_regular", source_id, score=0.6, detail={"cv": coefficient_of_variation, "mean_ms": mean})
        if coefficient_of_variation > 2.0 and mean < 50:
            return Anomaly("timing_burst", source_id, score=0.8, detail={"cv": coefficient_of_variation, "mean_ms": mean})
        return None

    # -- headers ----------------------------------------------------------------

    def detect_header_anomaly(self, source_id: str, headers: dict, baseline_headers: Iterable[str]) -> Optional[Anomaly]:
        baseline = {h.lower() for h in baseline_headers}
        present = {h.lower() for h in headers.keys()}
        missing = baseline - present

        # Missing headers a normal client always sends (accept, user-agent, ...).
        critical_missing = {h for h in missing if h in ("user-agent", "accept")}
        if critical_missing:
            return Anomaly(
                "header_missing", source_id, score=0.5,
                detail={"missing": sorted(critical_missing)},
            )

        ua = headers.get("user-agent") or headers.get("User-Agent", "")
        if not ua or len(ua) < 5:
            return Anomaly("header_suspicious_ua", source_id, score=0.4, detail={"user_agent": ua})
        return None

    # -- payload -------------------------------------------------------------

    def detect_payload_anomaly(self, source_id: str, payload: str, baseline_stats: dict) -> Optional[Anomaly]:
        """`baseline_stats` carries `mean_length` / `stdev_length` learned by
        learning_engine.confidence_growth's companion baseline recalculation.
        """
        length = len(payload)
        mean_length = baseline_stats.get("mean_length", length)
        stdev_length = baseline_stats.get("stdev_length", 1.0) or 1.0

        z_score = abs(length - mean_length) / stdev_length
        if z_score > 4:
            return Anomaly("payload_size_outlier", source_id, score=min(1.0, 0.3 + z_score / 10), detail={"z_score": z_score, "length": length})

        non_printable = sum(1 for c in payload if ord(c) < 9 or 13 < ord(c) < 32)
        if length and non_printable / length > 0.1:
            return Anomaly("payload_binary_noise", source_id, score=0.55, detail={"non_printable_ratio": non_printable / length})
        return None

    # -- behavioral -------------------------------------------------------------

    def detect_behavioral_anomaly(self, source_id: str, request_count: int, window_seconds: float, baseline_rps: float) -> Optional[Anomaly]:
        if window_seconds <= 0:
            return None
        observed_rps = request_count / window_seconds
        if baseline_rps <= 0:
            return None
        ratio = observed_rps / baseline_rps
        if ratio >= 5:
            return Anomaly(
                "behavioral_rate_spike", source_id, score=min(1.0, 0.4 + ratio / 20),
                detail={"observed_rps": observed_rps, "baseline_rps": baseline_rps, "ratio": ratio},
            )
        return None
