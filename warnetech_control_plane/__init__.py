"""Warnetech Control Plane.

The core intelligence layer for Warnetech Integrated Systems and Security.
Manages signatures, anomalies, scoring, learning, recovery, metrics,
retention, slicing, ghost copies, and database interactions for the
Warnetech threat-defense stack.

Typical wiring::

    from warnetech_control_plane import (
        ControlPlaneConfig, ControlPlaneState, SupabaseDatabase,
        SignatureEngine, AnomalyEngine, BehaviorEngine, ScoringEngine,
        LearningEngine, RecoveryEngine, MetricsEngine, RetentionEngine,
        SliceEngine, GhostEngine,
    )

    config = ControlPlaneConfig()
    state = ControlPlaneState(config)
    db = SupabaseDatabase(config)

    signatures = SignatureEngine(state, db, config)
    signatures.sync_cache()

    scoring = ScoringEngine(config)
    matches = signatures.match(payload)
    result = scoring.score(
        signature_score=matches[0]["score"] if matches else 0.0,
        behavioral_score=BehaviorEngine(config).rate_analysis(...),
        anomaly_score=0.0,
    )
"""

from .anomaly_engine import Anomaly, AnomalyEngine
from .behavior_engine import BehaviorEngine
from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .database import SupabaseDatabase
from .ghost_engine import (
    GhostEngine,
    GhostIndexEntry,
    GhostRecord,
    create_ghost_copy,
    fetch_ghost_copy,
    list_ghost_copies,
    store_ghost_copy,
    verify_ghost_integrity,
)
from .learning_engine import LearningEngine, ThresholdAdaptation
from .logging import get_logger
from .metrics_engine import MetricRollup, MetricsEngine
from .recovery_engine import RecoveryEngine, RecoveryReport, RecoveryStepResult
from .retention_engine import RetentionEngine, TierResult
from .scoring_engine import ScoreResult, ScoringEngine
from .signature_engine import Signature, SignatureEngine, signature_id
from .slice_engine import Slice, SliceEngine, SliceMetadata
from .state import ControlPlaneState

__version__ = "0.1.0"

__all__ = [
    "Anomaly",
    "AnomalyEngine",
    "BehaviorEngine",
    "ControlPlaneConfig",
    "DEFAULT_CONFIG",
    "SupabaseDatabase",
    "GhostEngine",
    "GhostIndexEntry",
    "GhostRecord",
    "create_ghost_copy",
    "fetch_ghost_copy",
    "list_ghost_copies",
    "store_ghost_copy",
    "verify_ghost_integrity",
    "LearningEngine",
    "ThresholdAdaptation",
    "get_logger",
    "MetricRollup",
    "MetricsEngine",
    "RecoveryEngine",
    "RecoveryReport",
    "RecoveryStepResult",
    "RetentionEngine",
    "TierResult",
    "ScoreResult",
    "ScoringEngine",
    "Signature",
    "SignatureEngine",
    "signature_id",
    "Slice",
    "SliceEngine",
    "SliceMetadata",
    "ControlPlaneState",
]
