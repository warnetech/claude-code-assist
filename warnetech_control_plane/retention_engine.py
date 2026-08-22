"""Retention policies for hot, warm, cold, and ghost tiers: downsampling,
compression, and deletion rules.

Tiers age data down rather than dropping it outright:

    hot (raw, `retention.hot_tier_hours`)
      -> warm (downsampled `retention.downsample_factor`:1, gzip'd, `retention.warm_tier_days`)
      -> cold (near-line, aged past warm but not yet ghost-eligible, `COLD_TIER_DAYS`)
      -> ghost (aggregates only, kept `retention.ghost_tier_days`)
      -> deleted

Each transition is a pure function over a list of records so it can be
tested without a clock or real storage.

Cold tier reads `retention.cold_tier_days` off `ControlPlaneConfig` if
present, else falls back to `COLD_TIER_DAYS` below — this is a new,
optional window, so existing `ControlPlaneConfig` instances that predate
it keep working unchanged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from . import ghost_engine
from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .database import SupabaseDatabase
from .logging import get_logger
from .utils import gzip_bytes, now_iso, sha256_hex, to_ndjson

logger = get_logger(__name__)

# Fallback cold-tier window when ControlPlaneConfig.retention has no
# cold_tier_days field of its own. Sits between warm_tier_days and
# ghost_tier_days by default.
COLD_TIER_DAYS = 90

# Ghost-trigger reasons, returned by determine_ghost_trigger() and stored
# verbatim as GhostRecord.metadata["retention_reason"] (via apply_ghost_tier).
GHOST_TRIGGER_WARM_EXPIRY = "warm_tier_expiry"
GHOST_TRIGGER_COLD_EXPIRY = "cold_tier_expiry"
GHOST_TRIGGER_COMPLIANCE_HOLD = "compliance_hold"
GHOST_TRIGGER_MANUAL = "manual_trigger"


@dataclass(frozen=True)
class TierResult:
    tier: str
    records_in: int
    records_out: int
    bytes_out: int
    ghost_id: Optional[str] = None


class RetentionEngine:
    def __init__(self, config: ControlPlaneConfig = DEFAULT_CONFIG, database: Optional[SupabaseDatabase] = None) -> None:
        self._config = config
        self._db = database

    def is_past_hot_tier(self, record_epoch_seconds: float, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        age_hours = (now - record_epoch_seconds) / 3600
        return age_hours >= self._config.retention.hot_tier_hours

    def is_past_warm_tier(self, record_epoch_seconds: float, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        age_days = (now - record_epoch_seconds) / 86400
        return age_days >= self._config.retention.warm_tier_days

    def is_past_ghost_tier(self, record_epoch_seconds: float, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        age_days = (now - record_epoch_seconds) / 86400
        return age_days >= self._config.retention.ghost_tier_days

    def is_past_cold_tier(self, record_epoch_seconds: float, now: float | None = None) -> bool:
        """New retention window, between warm and ghost. Reads
        `retention.cold_tier_days` if ControlPlaneConfig defines it, else
        falls back to module-level COLD_TIER_DAYS.
        """
        now = now if now is not None else time.time()
        cold_tier_days = getattr(self._config.retention, "cold_tier_days", COLD_TIER_DAYS)
        age_days = (now - record_epoch_seconds) / 86400
        return age_days >= cold_tier_days

    def determine_ghost_trigger(
        self,
        record_epoch_seconds: float,
        now: float | None = None,
        compliance_hold: bool = False,
        manual_reason: Optional[str] = None,
    ) -> Optional[str]:
        """Centralizes ghost-trigger rules: returns the reason a ghost copy
        should be created now, or None if none apply yet. Priority order —
        an explicit manual trigger or a compliance hold always fires
        regardless of age; otherwise age against the cold and warm windows,
        oldest-eligible-window first.
        """
        if manual_reason is not None:
            return manual_reason
        if compliance_hold:
            return GHOST_TRIGGER_COMPLIANCE_HOLD
        if self.is_past_cold_tier(record_epoch_seconds, now):
            return GHOST_TRIGGER_COLD_EXPIRY
        if self.is_past_warm_tier(record_epoch_seconds, now):
            return GHOST_TRIGGER_WARM_EXPIRY
        return None

    def downsample(self, records: list[dict]) -> list[dict]:
        """Keeps every Nth record, per `retention.downsample_factor`."""
        factor = max(1, self._config.retention.downsample_factor)
        return records[::factor]

    def apply_warm_tier(self, hot_records: list[dict]) -> TierResult:
        downsampled = self.downsample(hot_records)
        body = gzip_bytes(to_ndjson(downsampled).encode("utf-8"), level=self._config.compression.level)
        logger.info("warm tier applied", records_in=len(hot_records), records_out=len(downsampled), bytes_out=len(body))
        return TierResult(tier="warm", records_in=len(hot_records), records_out=len(downsampled), bytes_out=len(body))

    def apply_ghost_tier(
        self,
        warm_records: list[dict],
        aggregate_fn,
        slice_id: Optional[str] = None,
        domain: str = "unknown",
        time_start: str = "",
        time_end: str = "",
        retention_window: Optional[str] = None,
        retention_reason: Optional[str] = None,
    ) -> TierResult:
        """`aggregate_fn` collapses warm records into ghost-tier aggregates
        (typically metrics_engine's rollup math). Ghost tier stores only
        aggregates — no per-event detail survives past this point except
        what ghost_engine explicitly preserves as a ghost copy.

        `retention_window` and `retention_reason` are optional, additive
        metadata — e.g. "cold", determine_ghost_trigger()'s return value —
        folded into the slice_metadata dict handed to
        ghost_engine.create_ghost_copy(), which already merges the whole
        dict into GhostRecord.metadata verbatim. ghost_engine.py itself is
        unchanged; both fields are simply omitted from metadata when not
        supplied, exactly as before this change.

        The aggregate body is itself handed to ghost_engine.create_ghost_copy()
        / store_ghost_copy() so retention-driven ghost copies are created and
        indexed the same way explicit /ghost/create requests are. Creation is
        logged via log_retention_ghost_creation() (there is no dedicated
        ghost_log table; it still lands in security_events).
        """
        aggregates = aggregate_fn(warm_records)
        body = gzip_bytes(to_ndjson(aggregates).encode("utf-8"), level=self._config.compression.level)
        logger.info("ghost tier applied", records_in=len(warm_records), records_out=len(aggregates), bytes_out=len(body))

        resolved_slice_id = slice_id or f"retention-{now_iso()}"
        slice_metadata = {
            "slice_id": resolved_slice_id,
            "domain": domain,
            "time_start": time_start,
            "time_end": time_end,
            "record_count": len(aggregates),
            "sha256": sha256_hex(body),
            "compressed": True,
            "encrypted": False,
        }
        if retention_window is not None:
            slice_metadata["retention_window"] = retention_window
        if retention_reason is not None:
            slice_metadata["retention_reason"] = retention_reason

        ghost_record = ghost_engine.create_ghost_copy(slice_metadata, body, config=self._config, ghost_type="aggregate")
        ghost_engine.store_ghost_copy(ghost_record, config=self._config)

        if self._db is not None:
            self._db.log_retention_ghost_creation({
                "ghost_id": ghost_record.id,
                "slice_id": resolved_slice_id,
                "domain": domain,
                "size": ghost_record.size,
                "retention_window": retention_window,
                "retention_reason": retention_reason,
            })

        return TierResult(
            tier="ghost", records_in=len(warm_records), records_out=len(aggregates),
            bytes_out=len(body), ghost_id=ghost_record.id,
        )

    def enforce_deletion(self, records: list[dict], epoch_key: str = "epoch_seconds", now: float | None = None) -> list[dict]:
        """Returns only the records that are still within the ghost-tier
        retention window; everything older is dropped.
        """
        now = now if now is not None else time.time()
        kept = [r for r in records if not self.is_past_ghost_tier(r.get(epoch_key, now), now)]
        dropped = len(records) - len(kept)
        if dropped:
            logger.info("retention deletion enforced", dropped=dropped, kept=len(kept))
        return kept
