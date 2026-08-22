"""End-to-end: the Python CLI seals a request, a live warnetech_server opens
it, and the sealed reply is opened back on the client."""

import dataclasses
import json

import pytest

from warnetech_cli.config import Config
from warnetech_cli.server_client import ServerClient
from warnetech_envelope import is_envelope, seal, unseal

API_KEY = "test-api-key"


class _Cfg(Config):
    """Config that never touches disk."""

    def __init__(self, data):
        self.config_path = None
        self.data = data


def _client(**overrides):
    data = {"server_url": "http://localhost:8080", "api_key": API_KEY}
    data.update(overrides)
    return ServerClient(_Cfg(data))


# --------------------------------------------------------------------------
# Client-side sealing
# --------------------------------------------------------------------------


def test_client_seals_request_bodies(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}

        class _Resp:
            def read(self):
                return json.dumps(seal({"ok": True}, API_KEY)).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = _client().post("/score", {"payload": "sensitive-value"})

    assert is_envelope(captured["body"]), "request body was not sealed"
    assert "sensitive-value" not in json.dumps(captured["body"])
    assert unseal(captured["body"], API_KEY) == {"payload": "sensitive-value"}
    assert captured["headers"].get("X-Warnetech-Envelope".lower()) == "aes-256-gcm"
    assert result == {"ok": True}, "sealed response was not opened"


def test_client_refuses_to_send_without_an_api_key(monkeypatch):
    """The envelope is mandatory and the API key is the channel key, so a
    missing key must fail rather than silently downgrade to plaintext."""
    called = []
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: called.append(1)
    )

    result = _client(api_key="").post("/score", {"payload": "x"})

    assert "api_key" in result["error"]
    assert called == [], "a request was sent despite having no channel key"


def test_client_reports_undecryptable_response(monkeypatch):
    def fake_urlopen(req, timeout=None):
        class _Resp:
            def read(self):
                return json.dumps(seal({"ok": True}, "a-different-key")).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = _client().post("/score", {"x": 1})
    assert result["error"] == "response decryption failed"


# --------------------------------------------------------------------------
# Server-side opening, through the real middleware chain
# --------------------------------------------------------------------------


def _chain():
    from warnetech_server.config import ServerConfig
    from warnetech_server.middleware import RateLimiter, Request, Response, build_middleware_chain

    config = dataclasses.replace(ServerConfig(), api_key=API_KEY)  # frozen dataclass
    seen = {}

    def handler(req):
        seen["json_body"] = req.json_body
        return Response(status=200, body={"echo": req.json_body})

    limiter = RateLimiter(requests_per_minute=10_000, burst=10_000)
    chain = build_middleware_chain(config, limiter, handler)
    return chain, seen, Request


def test_server_opens_sealed_request_and_seals_reply():
    chain, seen, Request = _chain()
    envelope = seal({"command": "ping"}, API_KEY)

    response = chain(
        Request(
            method="POST",
            path="/score",
            headers={"authorization": f"Bearer {API_KEY}"},
            body=json.dumps(envelope).encode(),
        )
    )

    assert response.status == 200
    assert seen["json_body"] == {"command": "ping"}, "handler did not receive cleartext"
    assert is_envelope(response.body), "reply was not sealed"
    assert unseal(response.body, API_KEY) == {"echo": {"command": "ping"}}


def test_server_rejects_unopenable_envelope_fail_closed():
    chain, seen, Request = _chain()
    envelope = seal({"command": "ping"}, "attacker-key")

    response = chain(
        Request(
            method="POST",
            path="/score",
            headers={"authorization": f"Bearer {API_KEY}"},
            body=json.dumps(envelope).encode(),
        )
    )

    assert response.status == 400
    assert response.body["error"] == "invalid_envelope"
    assert "json_body" not in seen, "handler ran despite a failed decrypt"


def test_server_rejects_a_plaintext_body():
    """A body that is not an envelope is refused; the handler never runs."""
    chain, seen, Request = _chain()
    response = chain(
        Request(
            method="POST",
            path="/score",
            headers={"authorization": f"Bearer {API_KEY}"},
            body=json.dumps({"command": "ping"}).encode(),
        )
    )
    assert response.status == 400
    # Rejections from the envelope layer are plaintext: a client that failed
    # to seal correctly may have no usable key to open a sealed error with.
    assert response.body["error"] == "envelope_required"
    assert "json_body" not in seen


def test_bodyless_request_passes_and_reply_is_sealed():
    """GET and health checks carry nothing to seal, but still get a sealed
    reply so the channel stays uniform in one direction."""
    chain, seen, Request = _chain()
    response = chain(
        Request(
            method="GET",
            path="/status",
            headers={"authorization": f"Bearer {API_KEY}"},
            body=b"",
        )
    )
    assert response.status == 200
    assert is_envelope(response.body)


# --------------------------------------------------------------------------
# https:// hardening
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://[::1]:8080",
        "https://warnetech.example.com",
    ],
)
def test_allowed_server_urls(url):
    assert Config.validate_server_url(url) == url


@pytest.mark.parametrize(
    "url",
    ["http://warnetech.example.com", "http://192.168.1.10:8080", "http://evil.test"],
)
def test_remote_http_rejected(url):
    with pytest.raises(ValueError, match="https://"):
        Config.validate_server_url(url)


def test_non_http_scheme_rejected():
    with pytest.raises(ValueError, match="http:// or https://"):
        Config.validate_server_url("ftp://warnetech.example.com")


def test_empty_url_is_permitted():
    assert Config.validate_server_url("") == ""
