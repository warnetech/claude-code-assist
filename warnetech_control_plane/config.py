"""Configuration for the Warnetech Control Plane.

Centralizes every tunable used by the engines: scoring weights, learning
parameters, retention policy, compression settings, and recovery parameters.
Values default to what has already been verified in the sibling JS control
plane (warnet-control-plane/src/lib/scoring.js) so behavior stays consistent
across implementations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScoringWeights:
    """Weights for the unified threat scoring model.

    total = signature_score + behavioral_score * behavioral_weight
                             + anomaly_score * anomaly_weight

    The signature term is intentionally NOT diluted by a weight of its own —
    a confirmed signature match must dominate the score. Diluting it (e.g.
    signature * 0.4) previously let a 0.94-confidence match decay to 0.376
    and pass as LOW/ALLOW.
    """

    behavioral_weight: float = 0.3
    anomaly_weight: float = 0.2


@dataclass(frozen=True)
class ThreatThresholds:
    critical: float = 0.90
    high: float = 0.70
    medium: float = 0.40


@dataclass(frozen=True)
class LearningParams:
    """Signature reinforcement math, ported verbatim from Signature.reinforce()."""

    reinforcement_rate: float = 0.08
    penalty: float = 0.05
    max_weight: float = 0.95
    min_weight: float = 0.10
    confidence_floor: float = 0.10
    confidence_ceiling: float = 0.98
    saturation_weight: float = 0.95
    saturation_min_occurrences: int = 25


@dataclass(frozen=True)
class RetentionPolicy:
    hot_tier_hours: int = 24
    warm_tier_days: int = 30
    ghost_tier_days: int = 365
    downsample_factor: int = 10


@dataclass(frozen=True)
class CompressionSettings:
    algorithm: str = "gzip"
    level: int = 6


@dataclass(frozen=True)
class RecoveryParams:
    max_flush_batch: int = 500
    breach_lookback_hours: int = 72
    log_archive_prefix: str = "recovery-archives"


@dataclass(frozen=True)
class StateLimits:
    signature_cache_max: int = 5000
    metric_buffer_max: int = 20000
    threat_buffer_max: int = 5000
    anomaly_buffer_max: int = 2000


@dataclass(frozen=True)
class ControlPlaneConfig:
    """Root configuration. Reads overrides from environment variables so the
    same code runs unmodified in dev, staging, and production.
    """

    supabase_url: str = field(default_factory=lambda: os.environ.get("SUPABASE_URL", ""))
    supabase_key: str = field(default_factory=lambda: os.environ.get("SUPABASE_KEY", ""))
    backups_bucket: str = field(
        default_factory=lambda: os.environ.get("WARNETECH_BACKUPS_BUCKET", "warnetech-backups")
    )
    local_backup_dir: str = field(
        default_factory=lambda: os.environ.get("WARNETECH_LOCAL_BACKUP_DIR", "./.warnetech-backups")
    )

    scoring: ScoringWeights = field(default_factory=ScoringWeights)
    thresholds: ThreatThresholds = field(default_factory=ThreatThresholds)
    learning: LearningParams = field(default_factory=LearningParams)
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)
    compression: CompressionSettings = field(default_factory=CompressionSettings)
    recovery: RecoveryParams = field(default_factory=RecoveryParams)
    limits: StateLimits = field(default_factory=StateLimits)


DEFAULT_CONFIG = ControlPlaneConfig()
