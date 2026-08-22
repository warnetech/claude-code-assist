"""Unified scoring model: signature score + behavioral score + anomaly score,
combined with the learning engine's adaptation multiplier.

    total = signature_score + behavioral_score * behavioral_weight
                             + anomaly_score * anomaly_weight
    total = min(1.0, total * adaptation_multiplier)

This mirrors warnet-control-plane/src/lib/scoring.js exactly. The signature
term carries no weight of its own (i.e. weight 1.0) by design: diluting a
confirmed signature match (e.g. `signature_score * 0.4`) previously let a
0.94-confidence match decay to 0.376 and pass as LOW/ALLOW. Do not
reintroduce that dilution — the sibling JS implementation has a regression
test (`test/scoring.test.mjs`) guarding this exact formula.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import ControlPlaneConfig, DEFAULT_CONFIG


@dataclass(frozen=True)
class ScoreResult:
    total: float
    threat_level: str
    signature_score: float
    behavioral_score: float
    anomaly_score: float
    adaptation_multiplier: float


class ScoringEngine:
    def __init__(self, config: ControlPlaneConfig = DEFAULT_CONFIG) -> None:
        self._config = config

    def score(
        self,
        signature_score: float,
        behavioral_score: float = 0.0,
        anomaly_score: float = 0.0,
        adaptation_multiplier: float = 1.0,
    ) -> ScoreResult:
        weights = self._config.scoring
        raw = (
            signature_score
            + behavioral_score * weights.behavioral_weight
            + anomaly_score * weights.anomaly_weight
        )
        total = max(0.0, min(1.0, raw * adaptation_multiplier))
        return ScoreResult(
            total=total,
            threat_level=self.classify(total),
            signature_score=signature_score,
            behavioral_score=behavioral_score,
            anomaly_score=anomaly_score,
            adaptation_multiplier=adaptation_multiplier,
        )

    def classify(self, total: float) -> str:
        t = self._config.thresholds
        if total >= t.critical:
            return "CRITICAL"
        if total >= t.high:
            return "HIGH"
        if total >= t.medium:
            return "MEDIUM"
        return "LOW"

    def should_block(self, total: float) -> bool:
        return self.classify(total) in ("CRITICAL", "HIGH")
