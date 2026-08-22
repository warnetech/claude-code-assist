"""Integration: warnetech_cli -> warnetech-server, end to end.

Exercises the real path a command takes: Commands -> ServerClient (seals the
body in the canonical envelope) -> the real server middleware chain (opens it,
dispatches, seals the reply) -> ServerClient (opens the reply).

Adjusted from the original spec in two places, both against the real code:

  * There is no "ping" command in warnetech_cli; the equivalent is
    "server-ping", which calls Commands.server_ping().
  * main() returns an int exit code, not a string, so the "pong" assertion
    belongs on server_ping()'s return value rather than on main()'s.
"""

import dataclasses
import json

import pytest

from warnetech_cli.commands import Commands
from warnetech_cli.config import Config
from warnetech_envelope import is_envelope, unseal

API_KEY = "integration-test-key"


class _Cfg(Config):
    """Config that never touches disk."""

    def __init__(self, data):
        self.config_path = None
        self.data = data


@pytest.fixture
def config():
    return _Cfg({"server_url": "http://localhost:8080", "api_key": API_KEY, "log_level": "INFO"})


@pytest.fixture
def server():
    """The real middleware chain wrapping a stub /status route."""
    from warnetech_server.config import ServerConfig
    from warnetech_server.middleware import (
        RateLimiter,
        Request,
        Response,
        build_middleware_chain,
    )

    seen = {}

    def handler(req):
        seen["path"] = req.path
        seen["json_body"] = req.json_body
        return Response(status=200, body={"status": "ok", "service": "warnetech-server"})

    chain = build_middleware_chain(
        dataclasses.replace(ServerConfig(), api_key=API_KEY),
        RateLimiter(requests_per_minute=10_000, burst=10_000),
        handler,
    )
    return {"chain": chain, "seen": seen, "Request": Request}


@pytest.fixture
def wired(monkeypatch, server):
    """Route ServerClient's urllib calls into the live middleware chain."""
    traffic = {}

    def fake_urlopen(req, timeout=None):
        body = req.data or b""
        traffic["request_body"] = json.loads(body) if body else None

        response = server["chain"](
            server["Request"](
                method=req.get_method(),
                path="/status",
                headers={k.lower(): v for k, v in req.headers.items()},
                body=body,
            )
        )
        traffic["response_body"] = response.body
        payload = json.dumps(response.body).encode()

        class _Resp:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return traffic


# -- the flow ---------------------------------------------------------------


def test_ping_flow(config, wired):
    """The original spec's assertion, at the level that actually returns it."""
    result = Commands(config).server_ping()
    assert result["status"] == "pong"


def test_ping_reports_latency(config, wired):
    result = Commands(config).server_ping()
    assert isinstance(result["latency_ms"], float)
    assert result["server"] == "http://localhost:8080"


def test_unreachable_server_is_reported_not_raised(config, monkeypatch):
    import urllib.error

    def boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    result = Commands(config).server_ping()
    assert result["status"] == "unreachable"


# -- the envelope, across the wire ------------------------------------------


def test_request_body_is_sealed_on_the_wire(config, wired):
    Commands(config).client.post("/status", {"secret": "do-not-leak"})

    body = wired["request_body"]
    assert is_envelope(body)
    assert "do-not-leak" not in json.dumps(body)
    assert unseal(body, API_KEY) == {"secret": "do-not-leak"}


def test_server_receives_cleartext(config, wired, server):
    Commands(config).client.post("/status", {"command": "status"})
    assert server["seen"]["json_body"] == {"command": "status"}


def test_response_is_sealed_and_opened_by_the_client(config, wired):
    result = Commands(config).client.post("/status", {"command": "status"})

    assert is_envelope(wired["response_body"]), "server replied in cleartext"
    assert result == {"status": "ok", "service": "warnetech-server"}


def test_round_trip_survives_nested_structures(config, wired):
    payload = {"a": [1, 2, {"b": None}], "unicode": "ok", "deep": {"x": {"y": True}}}
    Commands(config).client.post("/status", payload)
    assert unseal(wired["request_body"], API_KEY) == payload


def test_wrong_key_is_rejected_fail_closed(config, wired, server):
    """A client sealing with the wrong key must not reach the handler."""
    from warnetech_cli.server_client import ServerClient

    bad = ServerClient(_Cfg({"server_url": "http://localhost:8080", "api_key": "wrong-key"}))
    result = bad.post("/status", {"command": "status"})

    assert "json_body" not in server["seen"]
    assert result.get("error") or result.get("detail")


# -- CLI entry point --------------------------------------------------------


def test_main_returns_exit_code(config, wired, monkeypatch):
    """main() returns an int, which is why the spec's `"pong" in result`
    could not have worked against it."""
    import importlib

    # warnetech_cli/__init__ re-exports the main() function, which shadows the
    # module of the same name, so import the module explicitly.
    cli_main = importlib.import_module("warnetech_cli.main")

    monkeypatch.setattr(cli_main, "Config", lambda *a, **k: config)
    code = cli_main.main(["server-ping"])
    assert isinstance(code, int)


def test_main_without_command_returns_1():
    from warnetech_cli.main import main

    assert main([]) == 1
