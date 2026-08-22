"""In-memory state for the control plane.

Holds the signature cache (hot path for scoring), and bounded buffers for
metrics, threat events, and anomalies that accumulate between flush cycles.
Every buffer is capped (see config.StateLimits) so a stalled downstream sink
can never grow this process without bound. All access is thread-safe.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Deque, Dict, Optional

from .config import ControlPlaneConfig, DEFAULT_CONFIG


class ControlPlaneState:
    def __init__(self, config: ControlPlaneConfig = DEFAULT_CONFIG) -> None:
        self._config = config
        self._lock = threading.RLock()

        self.signature_cache: Dict[str, dict] = {}
        self.metric_buffer: Deque[dict] = deque(maxlen=config.limits.metric_buffer_max)
        self.threat_buffer: Deque[dict] = deque(maxlen=config.limits.threat_buffer_max)
        self.anomaly_buffer: Deque[dict] = deque(maxlen=config.limits.anomaly_buffer_max)

        # Per-signature-id learning bookkeeping: occurrences, false_positives, etc.
        self.learning_state: Dict[str, dict] = {}

    # -- signature cache ----------------------------------------------------

    def upsert_signature(self, signature: dict) -> None:
        with self._lock:
            if len(self.signature_cache) >= self._config.limits.signature_cache_max:
                # Evict the least-reinforced entry to make room.
                weakest_id = min(
                    self.signature_cache, key=lambda sid: self.signature_cache[sid].get("weight", 0.0)
                )
                self.signature_cache.pop(weakest_id, None)
            self.signature_cache[signature["id"]] = signature

    def get_signature(self, signature_id: str) -> Optional[dict]:
        with self._lock:
            return self.signature_cache.get(signature_id)

    def all_signatures(self) -> list[dict]:
        with self._lock:
            return list(self.signature_cache.values())

    def replace_signature_cache(self, signatures: list[dict]) -> None:
        with self._lock:
            self.signature_cache = {s["id"]: s for s in signatures[: self._config.limits.signature_cache_max]}

    # -- buffers --------------------------------------------------------------

    def push_metric(self, metric: dict) -> None:
        with self._lock:
            self.metric_buffer.append(metric)

    def push_threat(self, event: dict) -> None:
        with self._lock:
            self.threat_buffer.append(event)

    def push_anomaly(self, anomaly: dict) -> None:
        with self._lock:
            self.anomaly_buffer.append(anomaly)

    def drain_metrics(self, max_items: Optional[int] = None) -> list[dict]:
        return self._drain(self.metric_buffer, max_items)

    def drain_threats(self, max_items: Optional[int] = None) -> list[dict]:
        return self._drain(self.threat_buffer, max_items)

    def drain_anomalies(self, max_items: Optional[int] = None) -> list[dict]:
        return self._drain(self.anomaly_buffer, max_items)

    def _drain(self, buf: Deque[dict], max_items: Optional[int]) -> list[dict]:
        with self._lock:
            n = len(buf) if max_items is None else min(max_items, len(buf))
            out = [buf.popleft() for _ in range(n)]
        return out

    # -- learning state -------------------------------------------------------

    def get_learning(self, signature_id: str) -> dict:
        with self._lock:
            return self.learning_state.setdefault(
                signature_id, {"occurrences": 0, "false_positives": 0, "true_positives": 0}
            )

    def update_learning(self, signature_id: str, **fields: Any) -> dict:
        with self._lock:
            entry = self.get_learning(signature_id)
            entry.update(fields)
            return entry

    def snapshot(self) -> dict:
        """A point-in-time view for diagnostics/health checks."""
        with self._lock:
            return {
                "signature_cache_size": len(self.signature_cache),
                "metric_buffer_size": len(self.metric_buffer),
                "threat_buffer_size": len(self.threat_buffer),
                "anomaly_buffer_size": len(self.anomaly_buffer),
                "learning_state_size": len(self.learning_state),
            }
