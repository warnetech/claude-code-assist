"""Warnetech Server.

The primary API and orchestration layer for Warnetech Integrated Systems
and Security. Exposes HTTP endpoints, integrates with the
warnetech-control-plane over HTTP, coordinates CLI operations via
warnetech-cli, runs containerised attack/defense tests in an isolated
protective field, and provides AI-assisted recall and defense-strategy
workflows.

Typical startup::

    from warnetech_server import WarnetechServerApp, ServerConfig

    app = WarnetechServerApp(ServerConfig())
    app.start(block=True)  # or block=False to run on a background thread
"""

from .app import WarnetechServerApp, main
from .config import ServerConfig, DEFAULT_CONFIG
from .middleware import Request, Response

__version__ = "0.1.0"

__all__ = [
    "WarnetechServerApp",
    "main",
    "ServerConfig",
    "DEFAULT_CONFIG",
    "Request",
    "Response",
]
