"""Wires warnetech_connectors into warnetech-server: fetches from external
security connectors and ranks/summarizes the results through
warnetech_ai_controller.security_intel.

All connector and AI-controller calls are in-process Python imports, same
wiring philosophy as control_plane_client.py and ai_integration.py (see
docs/WARNETECH-CANONICAL-WIRING-SPEC.txt decision 1). This module owns no
connector or ranking logic itself — it only sequences calls.

Persistence to Supabase happens inside warnetech_ai_controller.security_intel
itself (produce_intel_summary and rank_intel_relevance write directly to
ai_decisions and security_events), not here — persisting again at this
layer on top of that would double-write every record. See
warnetech_ai_controller/security_intel.py's docstring for the persistence
path.
"""

from __future__ import annotations

from typing import Optional

from .config import ServerConfig
from .logging import get_logger, log_ai_interaction

logger = get_logger(__name__)


class SecurityIntelIntegration:
    def __init__(self, config: ServerConfig) -> None:
        self._config = config

        try:
            from warnetech_connectors import intel_feeds, log_aggregators, reputation_services, siem_soar, vuln_databases
            from warnetech_connectors.config import ConnectorsConfig
        except ImportError as exc:  # pragma: no cover - repo layout dependent
            raise RuntimeError(
                "warnetech_connectors is required for security intel integration; "
                "ensure it is importable alongside warnetech_server"
            ) from exc

        try:
            from warnetech_ai_controller import controller as ai_controller
        except ImportError as exc:  # pragma: no cover - repo layout dependent
            raise RuntimeError(
                "warnetech_ai_controller is required for security intel integration; "
                "ensure it is importable alongside warnetech_server"
            ) from exc

        self._intel_feeds = intel_feeds
        self._reputation_services = reputation_services
        self._vuln_databases = vuln_databases
        self._log_aggregators = log_aggregators
        self._siem_soar = siem_soar
        self._connectors_config = ConnectorsConfig()
        self._ai_controller = ai_controller

    # -- direct connector pass-throughs ------------------------------------------------
    # warnetech-server can call any connector category directly for a single
    # lookup without going through the full gather-and-rank pipeline below.

    def fetch_intel(self, source: str) -> dict:
        return self._intel_feeds.fetch_intel_feed(source, self._connectors_config)

    def check_reputation(self, target: str, source: str = "malwarebytes") -> dict:
        return self._reputation_services.query_reputation(target, source, self._connectors_config)

    def fetch_vulnerabilities(self, source: str) -> dict:
        return self._vuln_databases.fetch_vuln_data(source, self._connectors_config)

    def push_logs(self, source: str, logs: list[dict]) -> dict:
        return self._log_aggregators.push_logs(source, logs, self._connectors_config)

    def pull_logs(self, source: str, query: dict) -> dict:
        return self._log_aggregators.pull_logs(source, query, self._connectors_config)

    def push_soar_events(self, events: list[dict], source: str = "primary_siem_soar") -> dict:
        return self._siem_soar.push_events(events, source, self._connectors_config)

    def pull_soar_incidents(self, query: dict, source: str = "primary_siem_soar") -> dict:
        return self._siem_soar.pull_incidents(query, source, self._connectors_config)

    # -- gather, rank, and persist ---------------------------------------------------------

    def gather_and_rank_intel(self, intel_sources: list[str], reputation_targets: Optional[list[tuple[str, str]]] = None) -> dict:
        """Fetches from every named intel feed source plus every
        (target, source) reputation lookup, normalizes everything into one
        list, and ranks it through warnetech_ai_controller.controller.
        integrate_external_intel() — which persists the result itself; see
        this module's docstring.
        """
        raw_records: list[dict] = []

        for source in intel_sources:
            fetch_result = self._intel_feeds.fetch_intel_feed(source, self._connectors_config)
            if fetch_result.get("status") == "ok":
                raw_records.extend(self._intel_feeds.normalize_intel(r) for r in fetch_result.get("records", []))

        for target, source in reputation_targets or []:
            query_result = self._reputation_services.query_reputation(target, source, self._connectors_config)
            if query_result.get("status") == "ok":
                raw_records.append(self._reputation_services.normalize_reputation(query_result))

        ranked = self._ai_controller.integrate_external_intel(raw_records)
        log_ai_interaction(logger, "gather_and_rank_intel", True, {"raw_count": len(raw_records), "ranked_count": len(ranked.get("ranked_intel", []))})
        return ranked
