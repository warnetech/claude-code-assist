"""Metric collection, rollups, aggregation, retention hand-off, and export
to warnetech-backups.

Raw samples live only in `ControlPlaneState.metric_buffer` — this engine
never writes raw time-series to Postgres, only the rollups it computes here,
matching the tiering strategy used across the rest of the control plane
(Postgres canonical for small relational state; bulk goes to blob storage).
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .database import SupabaseDatabase
from .logging import get_logger
from .state import ControlPlaneState
from .utils import now_iso, to_ndjson

logger = get_logger(__name__)


@dataclass(frozen=True)
class MetricRollup:
    metric_name: str
    source_id: str
    window_start: str
    window_end: str
    count: int
    min: float
    max: float
    mean: float
    p50: float
    p95: float
    p99: float
    stddev: float

    def to_dict(self) -> dict:
        return asdict(self)


class StorageBackend(Protocol):
    def put(self, key: str, data: bytes) -> None: ...


class LocalFileStorage:
    """Default storage backend: writes under `local_backup_dir`. Swap for a
    real R2/S3 client in production by passing any object with a
    ``put(key, data)`` method to MetricsEngine.
    """

    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)

    def put(self, key: str, data: bytes) -> None:
        path = self._base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(round(pct * (len(sorted_values) - 1))))
    return sorted_values[idx]


class MetricsEngine:
    def __init__(
        self,
        state: ControlPlaneState,
        database: SupabaseDatabase | None = None,
        storage: StorageBackend | None = None,
        config: ControlPlaneConfig = DEFAULT_CONFIG,
    ) -> None:
        self._state = state
        self._db = database
        self._config = config
        self._storage = storage or LocalFileStorage(config.local_backup_dir)

    def ingest(self, metric_name: str, source_id: str, value: float, timestamp: str | None = None) -> None:
        self._state.push_metric(
            {"metric_name": metric_name, "source_id": source_id, "value": value, "timestamp": timestamp or now_iso()}
        )

    def rollup(self, window_start: str, window_end: str) -> list[MetricRollup]:
        """Drains the buffer and aggregates by (metric_name, source_id).
        Never touches raw samples afterward — they are gone once drained,
        by design, so a slow rollup consumer can't cause unbounded growth.
        """
        raw = self._state.drain_metrics()
        grouped: dict[tuple[str, str], list[float]] = {}
        for record in raw:
            key = (record["metric_name"], record["source_id"])
            grouped.setdefault(key, []).append(record["value"])

        rollups: list[MetricRollup] = []
        for (metric_name, source_id), values in grouped.items():
            values.sort()
            rollups.append(
                MetricRollup(
                    metric_name=metric_name,
                    source_id=source_id,
                    window_start=window_start,
                    window_end=window_end,
                    count=len(values),
                    min=values[0],
                    max=values[-1],
                    mean=statistics.fmean(values),
                    p50=_percentile(values, 0.50),
                    p95=_percentile(values, 0.95),
                    p99=_percentile(values, 0.99),
                    stddev=statistics.pstdev(values) if len(values) > 1 else 0.0,
                )
            )
        logger.info("metrics rolled up", groups=len(rollups), raw_samples=len(raw))
        return rollups

    def flush_rollups(self, rollups: list[MetricRollup]) -> bool:
        if not rollups or self._db is None:
            return False
        return self._db.write_metrics([r.to_dict() for r in rollups])

    def export_raw_to_backups(self, raw_records: list[dict], partition_key: str) -> str:
        """Archives raw samples as NDJSON to warnetech-backups before they
        would otherwise be discarded by rollup(); the read path for bulk
        history is this archive, never Postgres.
        """
        key = f"metrics/{partition_key}/{now_iso().replace(':', '')}.ndjson"
        body = to_ndjson(raw_records).encode("utf-8")
        self._storage.put(key, body)
        logger.info("raw metrics exported", bucket=self._config.backups_bucket, key=key, records=len(raw_records))
        return key

    def maintain_partitions(self) -> dict:
        """Triggers both partition-maintenance RPCs — maintain_partitions()
        (metric_rollups and threat_events) and the dedicated
        maintain_threat_event_partitions() (threat_events only, redundant
        with the first by design). Meant to be called periodically by
        whatever scheduler this process runs under; this codebase has no
        in-process cron, so the caller (e.g. warnetech-server's own
        maintenance workflow) is responsible for triggering it on a
        schedule.
        """
        if self._db is None:
            logger.warning("maintain_partitions called with no database configured")
            return {"partitions_synced": False, "threat_event_partitions_synced": False}

        partitions_ok = self._db.sync_partitions()
        threat_event_partitions_ok = self._db.sync_threat_event_partitions()
        return {"partitions_synced": partitions_ok, "threat_event_partitions_synced": threat_event_partitions_ok}
