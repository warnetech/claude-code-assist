"""Claude-side orchestration layer for AI Firewall UKSCN1.

This module owns NO logic of its own. Every capability it exposes is a
composition of engines that already exist:

    warnetech_control_plane.scoring_engine   ScoringEngine
    warnetech_control_plane.anomaly_engine   AnomalyEngine
    warnetech_control_plane.ghost_engine     GhostEngine
    warnetech_control_plane.recovery_engine  RecoveryEngine
    warnetech_ai_controller.recall_planner   plan_ghost_recall,
                                             build_reconstruction_plan

It defines no new dataclasses that shadow existing ones -- in particular it
does NOT define a Signature type, because warnetech_control_plane.
signature_engine.Signature already exists and carries confidence,
occurrences and false_positives that a simpler copy would silently drop.

The point of this layer is a single entry point that sequences those engines
in the order the firewall actually uses them, so callers do not have to wire
five constructors together correctly every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from warnetech_control_plane.anomaly_engine import AnomalyEngine
from warnetech_control_plane.config import DEFAULT_CONFIG as CONTROL_PLANE_CONFIG
from warnetech_control_plane.config import ControlPlaneConfig
from warnetech_control_plane.ghost_engine import GhostEngine
from warnetech_control_plane.recovery_engine import RecoveryEngine
from warnetech_control_plane.scoring_engine import ScoringEngine
from warnetech_control_plane.signature_engine import SignatureEngine
from warnetech_control_plane.state import ControlPlaneState

from .config import DEFAULT_CONFIG as AI_CONFIG
from .config import AIControllerConfig
from .recall_planner import build_reconstruction_plan, plan_ghost_recall

__all__ = ["AssessmentResult", "WarnetechClaudeAgent"]


@dataclass
class AssessmentResult:
    """Outcome of assessing one request against the firewall."""

    threat_level: str
    total_score: float
    blocked: bool
    anomalies: list[dict] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "threat_level": self.threat_level,
            "total_score": self.total_score,
            "blocked": self.blocked,
            "anomalies": self.anomalies,
            "breakdown": self.breakdown,
        }


class WarnetechClaudeAgent:
    """Sequences the existing engines; holds no independent state."""

    def __init__(
        self,
        control_plane_config: ControlPlaneConfig = CONTROL_PLANE_CONFIG,
        ai_config: AIControllerConfig = AI_CONFIG,
        scoring: Optional[ScoringEngine] = None,
        anomaly: Optional[AnomalyEngine] = None,
        ghost: Optional[GhostEngine] = None,
        recovery: Optional[RecoveryEngine] = None,
        state: Optional[ControlPlaneState] = None,
        signatures: Optional[SignatureEngine] = None,
    ) -> None:
        self._ai_config = ai_config
        # Engines are injectable so tests and alternate deployments can
        # substitute them; the defaults are the real implementations.
        self.state = state or ControlPlaneState(control_plane_config)
        self.signatures = signatures or SignatureEngine(self.state, config=control_plane_config)
        self.scoring = scoring or ScoringEngine(control_plane_config)
        self.anomaly = anomaly or AnomalyEngine(control_plane_config)
        self.ghost = ghost or GhostEngine(control_plane_config)
        # RecoveryEngine requires state and signature_engine; absorbing that
        # wiring is the reason this layer exists.
        self.recovery = recovery or RecoveryEngine(
            state=self.state, signature_engine=self.signatures, config=control_plane_config
        )

    # -- assessment ---------------------------------------------------------

    def assess(
        self,
        source_id: str,
        signature_score: float,
        behavioral_score: float = 0.0,
        headers: Optional[dict] = None,
        baseline_headers: Optional[list[str]] = None,
        intervals_ms: Optional[list[float]] = None,
        adaptation_multiplier: float = 1.0,
    ) -> AssessmentResult:
        """Detect anomalies, fold them into the score, and decide to block.

        The anomaly score handed to ScoringEngine is the count of detected
        anomalies normalised to [0, 1], so a single detector firing cannot by
        itself saturate the score.
        """
        anomalies: list[dict] = []

        if intervals_ms:
            found = self.anomaly.detect_timing_anomaly(source_id, intervals_ms)
            if found:
                anomalies.append(found.to_dict())

        if headers is not None and baseline_headers is not None:
            found = self.anomaly.detect_header_anomaly(source_id, headers, baseline_headers)
            if found:
                anomalies.append(found.to_dict())

        anomaly_score = min(1.0, len(anomalies) / 3.0)

        result = self.scoring.score(
            signature_score=signature_score,
            behavioral_score=behavioral_score,
            anomaly_score=anomaly_score,
            adaptation_multiplier=adaptation_multiplier,
        )

        return AssessmentResult(
            threat_level=result.threat_level,
            total_score=result.total,
            blocked=self.scoring.should_block(result.total),
            anomalies=anomalies,
            breakdown={
                "signature_score": result.signature_score,
                "behavioral_score": result.behavioral_score,
                "anomaly_score": result.anomaly_score,
                "adaptation_multiplier": result.adaptation_multiplier,
            },
        )

    # -- recall -------------------------------------------------------------

    def plan_recall(
        self,
        ghost_copies: list[dict],
        query_embedding: Optional[list[float]] = None,
        system: Optional[str] = None,
        type_: Optional[str] = None,
        time_start: Optional[str] = None,
        time_end: Optional[str] = None,
        order: str = "relevance",
    ) -> dict:
        """Rank ghost copies and build the multi-ghost reconstruction plan.

        Both halves see the same candidate set and the same metadata
        filters, so the plan cannot describe steps the recall did not
        select.
        """
        plan = plan_ghost_recall(
            ghost_copies,
            query_embedding=query_embedding,
            config=self._ai_config,
            system=system,
            type_=type_,
            time_start=time_start,
            time_end=time_end,
        )
        reconstruction = build_reconstruction_plan(
            ghost_copies,
            system=system,
            type_=type_,
            order=order,
            window_start=time_start,
            window_end=time_end,
        )
        return {
            "recall_plan": plan,
            "reconstruction_plan": reconstruction.to_dict(),
            "total_steps": reconstruction.total_steps,
        }

    def recall_ghost(self, slice_id: str) -> Optional[bytes]:
        """Fetch a single ghost copy's payload by slice id."""
        return self.ghost.retrieve_ghost_copy(slice_id)

    # -- recovery -----------------------------------------------------------

    def recover(self, incident_id: str) -> dict:
        """Run the recovery protocol and report per-step results."""
        return self.recovery.run(incident_id).to_dict()

    # -- introspection ------------------------------------------------------

    def engines(self) -> dict[str, Any]:
        """The engines this agent orchestrates, for diagnostics."""
        return {
            "scoring": type(self.scoring).__name__,
            "anomaly": type(self.anomaly).__name__,
            "ghost": type(self.ghost).__name__,
            "recovery": type(self.recovery).__name__,
            "signatures": type(self.signatures).__name__,
        }
