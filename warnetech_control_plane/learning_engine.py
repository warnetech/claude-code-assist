"""Adaptive learning: signature creation, reinforcement orchestration,
threshold adaptation, confidence growth tracking, and pattern-saturation
detection.

`signature_engine.SignatureEngine` owns the actual weight/confidence math;
this module owns the policy layer above it — deciding *when* to mint a new
signature vs. reinforce an existing one, and how the global block threshold
should drift in response to observed false-positive/false-negative rates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .logging import get_logger
from .signature_engine import Signature, SignatureEngine
from .state import ControlPlaneState

logger = get_logger(__name__)


@dataclass(frozen=True)
class ThresholdAdaptation:
    previous: float
    updated: float
    reason: str


class LearningEngine:
    def __init__(
        self,
        state: ControlPlaneState,
        signature_engine: SignatureEngine,
        config: ControlPlaneConfig = DEFAULT_CONFIG,
    ) -> None:
        self._state = state
        self._signatures = signature_engine
        self._config = config

    def report_outcome(self, attack_type: str, pattern: str, matched_ids: list[str], true_positive: bool) -> Signature | dict | None:
        """Reinforces every signature that matched. Only mints a new
        signature when nothing matched — this is the fix for the
        duplicate-signature-spawning bug: a payload that already has three
        weak matching signatures must reinforce those, not mint a fourth.
        """
        if matched_ids:
            last = None
            for sig_id in matched_ids:
                last = self._signatures.reinforce(sig_id, true_positive)
            return last

        if true_positive:
            new_sig = self._signatures.create(attack_type, pattern)
            logger.info("no match found; new signature minted", signature_id=new_sig.id)
            return new_sig

        logger.info("no match and false positive reported; nothing to learn from")
        return None

    # -- threshold adaptation --------------------------------------------------

    def adapt_threshold(self, current_threshold: float, false_positive_rate: float, false_negative_rate: float) -> ThresholdAdaptation:
        """Nudges the block threshold toward fewer errors. Moves slowly (5%
        of the gap per call) so a single noisy window can't swing detection
        behavior.
        """
        step = 0.05
        if false_negative_rate > false_positive_rate * 1.5:
            # Missing real attacks matters more than a slightly higher
            # false-positive rate: lower the bar to block.
            updated = max(0.1, current_threshold - (current_threshold * step))
            reason = "false_negative_rate dominant"
        elif false_positive_rate > false_negative_rate * 1.5:
            updated = min(0.95, current_threshold + (current_threshold * step))
            reason = "false_positive_rate dominant"
        else:
            updated = current_threshold
            reason = "balanced"
        return ThresholdAdaptation(previous=current_threshold, updated=updated, reason=reason)

    # -- confidence growth -------------------------------------------------------

    def confidence_growth(self, signature_id: str) -> Optional[float]:
        """Returns the confidence delta since this signature was created,
        for trend reporting (see LEARNING-PROGRESSION.md-style exports).
        """
        sig = self._state.get_signature(signature_id)
        if sig is None:
            return None
        learning = self._state.get_learning(signature_id)
        occurrences = learning.get("occurrences", 0)
        if occurrences == 0:
            return 0.0
        return sig.get("confidence", 0.5) - 0.5  # 0.5 is the cold-start default

    # -- saturation ---------------------------------------------------------------

    def is_saturated(self, signature_id: str) -> bool:
        """A saturated signature has learned as much as it can from
        reinforcement alone — further true positives won't move its weight
        meaningfully. Saturated signatures are candidates for promotion to a
        stable/verified state rather than continued adaptive tuning.
        """
        sig = self._state.get_signature(signature_id)
        if sig is None:
            return False
        params = self._config.learning
        return (
            sig.get("weight", 0.0) >= params.saturation_weight
            and sig.get("occurrences", 0) >= params.saturation_min_occurrences
        )
