"""Configuration for warnetech-connectors: enabled_connectors, API keys and
endpoints for each external service, rate limits, timeout settings, retry
policies, and logging preferences.

Every endpoint/key is read from environment variables and defaults to
empty — a connector with no endpoint configured is simply disabled, never
a hardcoded call to a real third party. Names mirror
warnetech_server.config.SecurityConnectors (malwarebytes, HIBP, Norton,
McAfee) for the categories that map onto it; the newer categories
(vulnerability databases, log aggregation, SIEM/SOAR) follow the same
name/endpoint/env-var shape without assuming a specific vendor.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConnectorEndpoint:
    name: str
    endpoint: str = ""
    api_key: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint)


@dataclass(frozen=True)
class RateLimitSettings:
    requests_per_minute: int = 30


@dataclass(frozen=True)
class TimeoutSettings:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0


@dataclass(frozen=True)
class LoggingPreferences:
    log_requests: bool = True
    log_responses: bool = True
    log_errors: bool = True


def _intel_feeds() -> tuple[ConnectorEndpoint, ...]:
    return (
        ConnectorEndpoint(name="have_i_been_pwned", endpoint=os.environ.get("HIBP_ENDPOINT", ""), api_key=os.environ.get("HIBP_API_KEY", "")),
    )


def _reputation_services() -> tuple[ConnectorEndpoint, ...]:
    return (
        ConnectorEndpoint(name="malwarebytes", endpoint=os.environ.get("MALWAREBYTES_ENDPOINT", ""), api_key=os.environ.get("MALWAREBYTES_API_KEY", "")),
        ConnectorEndpoint(name="norton", endpoint=os.environ.get("NORTON_ENDPOINT", ""), api_key=os.environ.get("NORTON_API_KEY", "")),
        ConnectorEndpoint(name="mcafee", endpoint=os.environ.get("MCAFEE_ENDPOINT", ""), api_key=os.environ.get("MCAFEE_API_KEY", "")),
    )


def _vuln_databases() -> tuple[ConnectorEndpoint, ...]:
    return (
        ConnectorEndpoint(name="nvd", endpoint=os.environ.get("NVD_ENDPOINT", ""), api_key=os.environ.get("NVD_API_KEY", "")),
    )


def _log_aggregators() -> tuple[ConnectorEndpoint, ...]:
    return (
        ConnectorEndpoint(name="primary_log_aggregator", endpoint=os.environ.get("LOG_AGGREGATOR_ENDPOINT", ""), api_key=os.environ.get("LOG_AGGREGATOR_API_KEY", "")),
    )


def _siem_soar() -> tuple[ConnectorEndpoint, ...]:
    return (
        ConnectorEndpoint(name="primary_siem_soar", endpoint=os.environ.get("SIEM_SOAR_ENDPOINT", ""), api_key=os.environ.get("SIEM_SOAR_API_KEY", "")),
    )


@dataclass(frozen=True)
class ConnectorsConfig:
    enabled_connectors: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            name.strip() for name in os.environ.get("WARNETECH_ENABLED_CONNECTORS", "").split(",") if name.strip()
        )
    )
    intel_feeds: tuple[ConnectorEndpoint, ...] = field(default_factory=_intel_feeds)
    reputation_services: tuple[ConnectorEndpoint, ...] = field(default_factory=_reputation_services)
    vuln_databases: tuple[ConnectorEndpoint, ...] = field(default_factory=_vuln_databases)
    log_aggregators: tuple[ConnectorEndpoint, ...] = field(default_factory=_log_aggregators)
    siem_soar: tuple[ConnectorEndpoint, ...] = field(default_factory=_siem_soar)

    rate_limit: RateLimitSettings = field(default_factory=RateLimitSettings)
    timeout: TimeoutSettings = field(default_factory=TimeoutSettings)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    logging_preferences: LoggingPreferences = field(default_factory=LoggingPreferences)

    def is_enabled(self, connector_name: str) -> bool:
        """A connector is usable only if it has a configured endpoint AND
        (when `enabled_connectors` is non-empty) is explicitly listed —
        this lets an operator allowlist a subset without unsetting every
        other endpoint's environment variable.
        """
        if self.enabled_connectors and connector_name not in self.enabled_connectors:
            return False
        for group in (self.intel_feeds, self.reputation_services, self.vuln_databases, self.log_aggregators, self.siem_soar):
            for endpoint in group:
                if endpoint.name == connector_name:
                    return endpoint.enabled
        return False

    def find(self, connector_name: str) -> ConnectorEndpoint | None:
        for group in (self.intel_feeds, self.reputation_services, self.vuln_databases, self.log_aggregators, self.siem_soar):
            for endpoint in group:
                if endpoint.name == connector_name:
                    return endpoint
        return None


DEFAULT_CONFIG = ConnectorsConfig()
