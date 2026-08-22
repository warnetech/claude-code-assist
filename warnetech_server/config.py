"""Configuration for warnetech-server: host/port, database connection,
retention/compression defaults, test-harness settings, and external
security service connectors.

Per docs/WARNETECH-CANONICAL-WIRING-SPEC.txt decision 1, warnetech-control-plane
is invoked in-process via direct Python imports, not over HTTP — there is
no control-plane endpoint to configure here. control_plane_client.py
constructs warnetech_control_plane's own ControlPlaneConfig directly, which
reads SUPABASE_URL/SUPABASE_KEY independently (see decision 2: both packages
point at the same Supabase project via those two environment variables).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatabaseSettings:
    supabase_url: str = field(default_factory=lambda: os.environ.get("SUPABASE_URL", ""))
    supabase_key: str = field(default_factory=lambda: os.environ.get("SUPABASE_KEY", ""))
    request_timeout_seconds: int = 10


@dataclass(frozen=True)
class RetentionDefaults:
    hot_tier_hours: int = 24
    warm_tier_days: int = 30
    ghost_tier_days: int = 365
    downsample_factor: int = 10


@dataclass(frozen=True)
class CompressionDefaults:
    algorithm: str = "gzip"
    level: int = 6


@dataclass(frozen=True)
class TestHarnessSettings:
    container_image_allowlist: tuple[str, ...] = ("warnetech/attack-sim:latest", "warnetech/defense-sim:latest")
    max_concurrent_containers: int = 4
    container_memory_limit_mb: int = 256
    container_cpu_limit: float = 1.0
    container_network_mode: str = "none"  # isolation: no network by default
    test_timeout_seconds: int = 120


@dataclass(frozen=True)
class SecurityConnectors:
    """Names/endpoints only — never credentials. Each is optional; an empty
    string means the connector is not configured.
    """

    malwarebytes_endpoint: str = field(default_factory=lambda: os.environ.get("MALWAREBYTES_ENDPOINT", ""))
    have_i_been_pwned_endpoint: str = field(default_factory=lambda: os.environ.get("HIBP_ENDPOINT", ""))
    norton_endpoint: str = field(default_factory=lambda: os.environ.get("NORTON_ENDPOINT", ""))
    mcafee_endpoint: str = field(default_factory=lambda: os.environ.get("MCAFEE_ENDPOINT", ""))


@dataclass(frozen=True)
class ConnectorCategoryToggles:
    """Enables or disables whole connector categories independent of
    whether individual endpoints are configured — see
    warnetech_connectors.config.ConnectorsConfig for the endpoints
    themselves. A category can be off here even with an endpoint set
    (e.g. to pause SIEM/SOAR pushes without unsetting its URL).
    """

    intel_feeds_enabled: bool = field(default_factory=lambda: os.environ.get("WARNETECH_INTEL_FEEDS_ENABLED", "true").lower() == "true")
    reputation_services_enabled: bool = field(default_factory=lambda: os.environ.get("WARNETECH_REPUTATION_SERVICES_ENABLED", "true").lower() == "true")
    vuln_databases_enabled: bool = field(default_factory=lambda: os.environ.get("WARNETECH_VULN_DATABASES_ENABLED", "true").lower() == "true")
    log_aggregators_enabled: bool = field(default_factory=lambda: os.environ.get("WARNETECH_LOG_AGGREGATORS_ENABLED", "false").lower() == "true")
    siem_soar_enabled: bool = field(default_factory=lambda: os.environ.get("WARNETECH_SIEM_SOAR_ENABLED", "false").lower() == "true")


@dataclass(frozen=True)
class RateLimitSettings:
    requests_per_minute: int = 120
    burst: int = 20


@dataclass(frozen=True)
class ServerConfig:
    host: str = field(default_factory=lambda: os.environ.get("WARNETECH_SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("WARNETECH_SERVER_PORT", "8080")))

    api_key: str = field(default_factory=lambda: os.environ.get("API_KEY", ""))
    auth_token_secret: str = field(default_factory=lambda: os.environ.get("WARNETECH_AUTH_SECRET", ""))

    cli_entrypoint: str = field(default_factory=lambda: os.environ.get("WARNETECH_CLI_ENTRYPOINT", "warnetech_cli_legacy/warnetech"))
    cli_timeout_seconds: int = 30

    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    retention: RetentionDefaults = field(default_factory=RetentionDefaults)
    compression: CompressionDefaults = field(default_factory=CompressionDefaults)
    test_harness: TestHarnessSettings = field(default_factory=TestHarnessSettings)
    security_connectors: SecurityConnectors = field(default_factory=SecurityConnectors)
    connector_toggles: ConnectorCategoryToggles = field(default_factory=ConnectorCategoryToggles)
    rate_limit: RateLimitSettings = field(default_factory=RateLimitSettings)


DEFAULT_CONFIG = ServerConfig()
