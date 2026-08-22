"""Test harness for containerised autonomous tests: defining test scenarios
for attacks and defenses, running tests in isolated containers, collecting
metrics and logs from tests, storing test results in the database, and
providing APIs to query test outcomes.

Composes container_runner.ContainerRunner (isolation) and database.ServerDatabase
(persistence); test_harness itself holds no I/O beyond what those two provide.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Optional

from .container_runner import ContainerRunner, PREDEFINED_PROFILES
from .database import ServerDatabase
from .logging import get_logger, log_test_run
from .utils import new_id, now_iso

logger = get_logger(__name__)


@dataclass
class TestScenario:
    id: str
    name: str
    kind: str  # "attack" | "defense"
    container_profile: str
    payloads: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TestResult:
    test_id: str
    scenario_id: str
    scenario_name: str
    kind: str
    payload_count: int
    success_count: int
    failure_count: int
    mean_duration_ms: float
    started_at: str
    finished_at: str
    logs: list[dict] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.payload_count if self.payload_count else 0.0

    def to_dict(self) -> dict:
        return {**asdict(self), "success_rate": self.success_rate}


class TestHarness:
    def __init__(self, container_runner: ContainerRunner, database: Optional[ServerDatabase] = None) -> None:
        self._runner = container_runner
        self._db = database
        self._local_results: dict[str, TestResult] = {}

    def define_scenario(self, name: str, kind: str, container_profile: str, payloads: list[str]) -> TestScenario:
        if container_profile not in PREDEFINED_PROFILES:
            raise ValueError(f"unknown container profile '{container_profile}'")
        if kind not in ("attack", "defense"):
            raise ValueError("kind must be 'attack' or 'defense'")
        return TestScenario(id=new_id("scenario"), name=name, kind=kind, container_profile=container_profile, payloads=payloads)

    def run_scenario(self, scenario: TestScenario) -> TestResult:
        test_id = new_id("test")
        started_at = now_iso()
        logs: list[dict] = []
        durations: list[float] = []
        success_count = 0

        for payload in scenario.payloads:
            profile = PREDEFINED_PROFILES[scenario.container_profile]
            run_result = self._runner.run(profile, payload)
            durations.append(run_result.duration_ms)
            if run_result.ok:
                success_count += 1
            logs.append({
                "payload_preview": payload[:200],
                "ok": run_result.ok,
                "exit_code": run_result.exit_code,
                "duration_ms": run_result.duration_ms,
                "stderr_preview": run_result.stderr[:500],
            })

        finished_at = now_iso()
        result = TestResult(
            test_id=test_id,
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            kind=scenario.kind,
            payload_count=len(scenario.payloads),
            success_count=success_count,
            failure_count=len(scenario.payloads) - success_count,
            mean_duration_ms=statistics.fmean(durations) if durations else 0.0,
            started_at=started_at,
            finished_at=finished_at,
            logs=logs,
        )

        self._local_results[test_id] = result
        log_test_run(logger, test_id, scenario.name, "complete", result.mean_duration_ms)

        if self._db is not None:
            self._db.store_test_result(result.to_dict())

        return result

    def query_results(self, test_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        if test_id:
            local = self._local_results.get(test_id)
            if local:
                return [local.to_dict()]

        if self._db is not None:
            remote = self._db.read_test_results(test_id=test_id, limit=limit)
            if remote:
                return remote

        results = list(self._local_results.values())
        if test_id:
            results = [r for r in results if r.test_id == test_id]
        return [r.to_dict() for r in results[-limit:]]
