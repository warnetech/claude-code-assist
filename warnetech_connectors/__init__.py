"""Warnetech Connectors.

External security connectors for Warnetech Integrated Systems and
Security: threat intelligence feeds, IP/domain reputation services,
vulnerability databases, log aggregation platforms, and SIEM/SOAR systems.

Every connector is enabled or disabled purely by whether its endpoint is
configured (see config.ConnectorsConfig) — there is no code path that
calls a real third party without an explicit endpoint being set. All data
flows are logged via logging.get_logger() and none of the "push_*"
functions mutate production data directly; they accept a `sink` callable
the caller supplies, so the actual delivery target (a control-plane
buffer, a database write) stays the caller's decision.

warnetech_server wires these into warnetech_ai_controller.security_intel
for ranking/summarization — see
warnetech_server/security_intel_integration.py.
"""

from .config import ConnectorsConfig, DEFAULT_CONFIG
from .logging import get_logger

__version__ = "0.1.0"

__all__ = [
    "ConnectorsConfig",
    "DEFAULT_CONFIG",
    "get_logger",
]
