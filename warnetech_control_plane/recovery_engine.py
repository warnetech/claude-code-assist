"""Full recovery protocol: connection flush, signature refresh, rule
restoration, breach vector analysis, vulnerability reinforcement, log
clearing, and incident notification.

Steps run in a fixed order because each depends on state the previous step
establishes (e.g. breach analysis needs a freshly-synced signature set, and
reinforcement needs the breach analysis's findings). A failed step does not
abort the run — it's recorded and the protocol continues, so one bad step
(e.g. an unreachable notification webhook) can't leave the system stuck
mid-recovery with connections still flushed but rules not restored.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .database import SupabaseDatabase
from .logging import get_logger
from .signature_engine import SignatureEngine
from .state import ControlPlaneState
from .utils import now_iso, write_ndjson

logger = get_logger(__name__)


@dataclass
class RecoveryStepResult:
    name: str
    status: str  # "ok" | "failed" | "skipped"
    duration_ms: float
    detail: dict = field(default_factory=dict)


@dataclass
class RecoveryReport:
    started_at: str
    finished_at: str
    steps: list[RecoveryStepResult]

    @property
    def all_ok(self) -> bool:
        return all(s.status == "ok" for s in self.steps)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "all_ok": self.all_ok,
            "steps": [asdict(s) for s in self.steps],
        }


NotifyFn = Callable[[str, dict], None]


class RecoveryEngine:
    def __init__(
        self,
        state: ControlPlaneState,
        signature_engine: SignatureEngine,
        database: Optional[SupabaseDatabase] = None,
        config: ControlPlaneConfig = DEFAULT_CONFIG,
        notify_fn: Optional[NotifyFn] = None,
    ) -> None:
        self._state = state
        self._signatures = signature_engine
        self._db = database
        self._config = config
        self._notify_fn = notify_fn or self._default_notify

    def run(self, incident_id: str) -> RecoveryReport:
        started_at = now_iso()
        steps: list[RecoveryStepResult] = []

        steps.append(self._run_step("flush_connections", self._flush_connections))
        steps.append(self._run_step("refresh_signatures", self._refresh_signatures))
        steps.append(self._run_step("restore_rules", self._restore_rules))
        breach_step = self._run_step("analyze_breach_vectors", self._analyze_breach_vectors)
        steps.append(breach_step)
        steps.append(self._run_step("reinforce_vulnerabilities", lambda: self._reinforce_vulnerabilities(breach_step.detail)))
        steps.append(self._run_step("clear_logs", self._clear_logs))
        steps.append(self._run_step("notify_incident", lambda: self._notify_incident(incident_id, steps)))

        report = RecoveryReport(started_at=started_at, finished_at=now_iso(), steps=steps)
        logger.info("recovery protocol complete", incident_id=incident_id, all_ok=report.all_ok)
        return report

    def _run_step(self, name: str, fn: Callable[[], dict]) -> RecoveryStepResult:
        start = time.monotonic()
        try:
            detail = fn() or {}
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - recovery must not abort on step failure
            detail = {"error": str(exc)}
            status = "failed"
            logger.error("recovery step failed", step=name, error=str(exc))
        duration_ms = (time.monotonic() - start) * 1000
        return RecoveryStepResult(name=name, status=status, duration_ms=duration_ms, detail=detail)

    # -- steps ------------------------------------------------------------------

    def _flush_connections(self) -> dict:
        drained_metrics = len(self._state.drain_metrics())
        drained_threats = len(self._state.drain_threats())
        drained_anomalies = len(self._state.drain_anomalies())
        return {"drained_metrics": drained_metrics, "drained_threats": drained_threats, "drained_anomalies": drained_anomalies}

    def _refresh_signatures(self) -> dict:
        count = self._signatures.sync_cache()
        return {"signatures_loaded": count}

    def _restore_rules(self) -> dict:
        # Rule restoration re-derives from the freshly-synced signature
        # cache rather than a separate rules store, so there is nothing to
        # drift out of sync.
        active = [s for s in self._state.all_signatures() if s.get("weight", 0) >= self._config.learning.min_weight]
        return {"active_rules": len(active)}

    def _analyze_breach_vectors(self) -> dict:
        if self._db is None:
            return {"anomalies_reviewed": 0, "suspect_signature_ids": []}
        anomalies = self._db.read_anomalies(status="open", limit=500)
        suspect_ids = sorted({a.get("related_signature_id") for a in anomalies if a.get("related_signature_id")})
        return {"anomalies_reviewed": len(anomalies), "suspect_signature_ids": suspect_ids}

    def _reinforce_vulnerabilities(self, breach_detail: dict) -> dict:
        suspect_ids = breach_detail.get("suspect_signature_ids", [])
        reinforced = 0
        for sig_id in suspect_ids:
            if self._signatures.reinforce(sig_id, true_positive=True) is not None:
                reinforced += 1
        return {"signatures_reinforced": reinforced}

    def _clear_logs(self) -> dict:
        """Archives buffered events to NDJSON before clearing, mirroring the
        DROP-PARTITION-not-DELETE principle: never discard without a copy.
        """
        threats = self._state.drain_threats()
        path = f"{self._config.recovery.log_archive_prefix}/threats-{now_iso().replace(':', '')}.ndjson"
        written = write_ndjson(path, threats) if threats else 0
        return {"archived_path": path, "records_archived": written}

    def _notify_incident(self, incident_id: str, steps: list[RecoveryStepResult]) -> dict:
        summary = {
            "incident_id": incident_id,
            "steps_ok": sum(1 for s in steps if s.status == "ok"),
            "steps_failed": sum(1 for s in steps if s.status == "failed"),
        }
        self._notify_fn(incident_id, summary)
        return summary

    def _default_notify(self, incident_id: str, summary: dict) -> None:
        fields = {k: v for k, v in summary.items() if k != "incident_id"}
        logger.info("incident notification", incident_id=incident_id, **fields)
