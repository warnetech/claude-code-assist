"""Main application object and server startup logic: API lifecycle,
request handling, and shutdown hooks.

Built on `http.server.ThreadingHTTPServer` rather than a web framework —
CLAUDE.md's "add heavy dependencies without justification" applies here,
and every route this server exposes is simple enough that the standard
library's request/response cycle is sufficient. Swapping in a framework
later would only touch this file and middleware.py's `Request`/`Response`
adapter boundary.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qsl

from .ai_integration import AIIntegration
from .cli_integration import CLIIntegration
from .config import ServerConfig, DEFAULT_CONFIG
from .container_runner import ContainerRunner
from .control_plane_client import ControlPlaneClient
from .database import ServerDatabase
from .logging import get_logger
from .middleware import RateLimiter, Request, build_middleware_chain, serialize_response
from .routes import ServerDependencies, build_router
from .security_intel_integration import SecurityIntelIntegration
from .test_harness import TestHarness

logger = get_logger(__name__)


def _make_handler_class(config: ServerConfig, deps: ServerDependencies, router, rate_limiter: RateLimiter):
    middleware_handler = build_middleware_chain(config, rate_limiter, lambda req: router.dispatch(req, deps))

    class _Handler(BaseHTTPRequestHandler):
        server_version = "warnetech-server/0.1"

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - stdlib signature
            pass  # structured logging happens in middleware; suppress default stderr noise

        def _handle(self, method: str) -> None:
            parsed = urlsplit(self.path)
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length > 0 else b""
            headers = {k.lower(): v for k, v in self.headers.items()}
            query = dict(parse_qsl(parsed.query))

            req = Request(
                method=method,
                path=parsed.path,
                headers=headers,
                body=body,
                query=query,
                remote_addr=self.client_address[0] if self.client_address else "unknown",
            )
            response = middleware_handler(req)
            payload = serialize_response(response)

            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 - stdlib method name
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802 - stdlib method name
            self._handle("POST")

    return _Handler


class WarnetechServerApp:
    """Owns the process lifecycle: construct dependencies once, start the
    HTTP server on a background thread, and expose start()/stop() so a
    caller (a script, a test, or a supervisor) controls its lifetime.
    """

    def __init__(self, config: ServerConfig = DEFAULT_CONFIG) -> None:
        self._config = config
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.deps = self._build_dependencies(config)
        self._router = build_router()
        self._rate_limiter = RateLimiter(config.rate_limit.requests_per_minute, config.rate_limit.burst)

    def _build_dependencies(self, config: ServerConfig) -> ServerDependencies:
        try:
            ai = AIIntegration()
        except RuntimeError as exc:
            logger.warning("ai integration unavailable at startup", reason=str(exc))
            ai = None

        container_runner = ContainerRunner(config)
        database = ServerDatabase(config)

        try:
            security_intel = SecurityIntelIntegration(config)
        except RuntimeError as exc:
            logger.warning("security intel integration unavailable at startup", reason=str(exc))
            security_intel = None

        return ServerDependencies(
            config=config,
            control_plane=ControlPlaneClient(config),
            database=database,
            cli=CLIIntegration(config),
            ai=ai,
            test_harness=TestHarness(container_runner, database),
            security_intel=security_intel,
        )

    def start(self, block: bool = False) -> None:
        handler_class = _make_handler_class(self._config, self.deps, self._router, self._rate_limiter)
        self._server = ThreadingHTTPServer((self._config.host, self._config.port), handler_class)
        logger.info("server starting", host=self._config.host, port=self._config.port)

        if block:
            try:
                self._server.serve_forever()
            finally:
                self.stop()
            return

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            logger.info("server shutting down")
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def bound_port(self) -> int:
        if self._server is None:
            raise RuntimeError("server has not been started")
        return self._server.server_address[1]


def main() -> None:
    app = WarnetechServerApp(DEFAULT_CONFIG)
    app.start(block=True)


if __name__ == "__main__":
    main()
