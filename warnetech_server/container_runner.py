"""Container orchestration for tests: launching containers with predefined
profiles, limiting resources for safety, running offensive and defensive
simulations, and ensuring tests run in a protective field isolated from
production.

Isolation is enforced two ways: `--network none` by default (no path out of
the container at all) and hard memory/CPU ceilings taken from
`config.test_harness`, checked *before* the container ever launches — a
profile that requests more than the configured maximum is refused, not
clamped, so a misconfigured scenario fails loudly instead of silently
running under-isolated.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass

from .config import ServerConfig
from .logging import get_logger

logger = get_logger(__name__)


class ContainerRunnerError(Exception):
    pass


@dataclass(frozen=True)
class ContainerProfile:
    name: str
    image: str
    memory_limit_mb: int
    cpu_limit: float
    network_mode: str = "none"
    timeout_seconds: int = 120


PREDEFINED_PROFILES: dict[str, ContainerProfile] = {
    "attack-sim": ContainerProfile(name="attack-sim", image="warnetech/attack-sim:latest", memory_limit_mb=256, cpu_limit=1.0, network_mode="none", timeout_seconds=120),
    "defense-sim": ContainerProfile(name="defense-sim", image="warnetech/defense-sim:latest", memory_limit_mb=256, cpu_limit=1.0, network_mode="none", timeout_seconds=120),
}


@dataclass(frozen=True)
class ContainerRunResult:
    profile: str
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float


class ContainerRunner:
    def __init__(self, config: ServerConfig) -> None:
        self._config = config

    def _docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def _validate_profile(self, profile: ContainerProfile) -> None:
        limits = self._config.test_harness
        if profile.image not in limits.container_image_allowlist:
            raise ContainerRunnerError(f"image '{profile.image}' is not in the allowlist")
        if profile.memory_limit_mb > limits.container_memory_limit_mb:
            raise ContainerRunnerError(f"memory_limit_mb {profile.memory_limit_mb} exceeds configured maximum {limits.container_memory_limit_mb}")
        if profile.cpu_limit > limits.container_cpu_limit:
            raise ContainerRunnerError(f"cpu_limit {profile.cpu_limit} exceeds configured maximum {limits.container_cpu_limit}")
        if profile.network_mode != "none" and limits.container_network_mode == "none":
            raise ContainerRunnerError("this deployment requires network_mode='none' for all test containers")

    def run(self, profile: ContainerProfile, payload: str) -> ContainerRunResult:
        self._validate_profile(profile)

        if not self._docker_available():
            logger.warning("docker not available; container run skipped", profile=profile.name)
            return ContainerRunResult(profile=profile.name, ok=False, exit_code=127, stdout="", stderr="docker is not installed or not on PATH", duration_ms=0.0)

        cmd = [
            "docker", "run", "--rm",
            "--network", profile.network_mode,
            "--memory", f"{profile.memory_limit_mb}m",
            "--cpus", str(profile.cpu_limit),
            "--pull", "never",
            profile.image,
        ]

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                input=payload,
                capture_output=True,
                text=True,
                timeout=profile.timeout_seconds,
            )
            duration_ms = (time.monotonic() - start) * 1000
            result = ContainerRunResult(profile=profile.name, ok=proc.returncode == 0, exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, duration_ms=duration_ms)
        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - start) * 1000
            result = ContainerRunResult(profile=profile.name, ok=False, exit_code=124, stdout="", stderr="container run timed out", duration_ms=duration_ms)
        except OSError as exc:
            duration_ms = (time.monotonic() - start) * 1000
            result = ContainerRunResult(profile=profile.name, ok=False, exit_code=126, stdout="", stderr=str(exc), duration_ms=duration_ms)

        logger.info("container run complete", profile=profile.name, ok=result.ok, duration_ms=result.duration_ms)
        return result

    def run_profile_by_name(self, profile_name: str, payload: str) -> ContainerRunResult:
        profile = PREDEFINED_PROFILES.get(profile_name)
        if profile is None:
            raise ContainerRunnerError(f"unknown profile '{profile_name}'")
        return self.run(profile, payload)
