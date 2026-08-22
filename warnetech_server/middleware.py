"""Middleware: authentication and authorization, rate limiting, request
validation, structured logging, error handling, and security headers.

Middlewares compose around a route handler as a chain, outermost first:

    error_handling(security_headers(logging(rate_limit(
        validate(envelope(auth(handler)))))))

so an auth failure is logged and rate-limited exactly like a success, and
any exception anywhere in the chain still gets security headers and a safe
JSON error body rather than a raw traceback.

The envelope layer sits between validation and auth: the body must parse as
JSON before it can be recognised as an envelope, and it must be decrypted
before auth or any route sees the cleartext it carries.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from warnetech_envelope import EnvelopeError, is_envelope, seal, unseal

from .auth import authenticate
from .config import ServerConfig
from .logging import get_logger, log_request, log_security_event
from .security import ValidationError, clamp_body_size, sanitize_output
from .utils import new_id, now_iso, to_json_bytes

logger = get_logger(__name__)

MAX_BODY_BYTES = 1_000_000  # 1 MB


@dataclass
class Request:
    method: str
    path: str
    headers: dict
    body: bytes
    query: dict = field(default_factory=dict)
    remote_addr: str = "unknown"
    request_id: str = field(default_factory=lambda: new_id("req"))
    principal: Optional[str] = None
    json_body: Optional[dict] = None


@dataclass
class Response:
    status: int
    body: dict
    headers: dict = field(default_factory=dict)


Handler = Callable[[Request], Response]


class RateLimiter:
    """A per-principal token bucket. One bucket refills continuously at
    `requests_per_minute / 60` tokens/sec, capped at `burst`.
    """

    def __init__(self, requests_per_minute: int, burst: int) -> None:
        self._rate_per_second = requests_per_minute / 60.0
        self._burst = burst
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_refill)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last_refill = self._buckets.get(key, (float(self._burst), now))
            tokens = min(self._burst, tokens + (now - last_refill) * self._rate_per_second)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            return True


def security_headers() -> dict:
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'",
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
        "Referrer-Policy": "no-referrer",
    }


def build_middleware_chain(config: ServerConfig, rate_limiter: RateLimiter, handler: Handler) -> Handler:
    def with_auth(req: Request) -> Response:
        result = authenticate(config, req.headers)
        if not result.ok:
            log_security_event(logger, "auth_failure", "medium", {"reason": result.reason, "path": req.path})
            return Response(status=401, body={"error": "unauthorized", "reason": result.reason})
        req.principal = result.principal
        return handler(req)

    def with_validation(req: Request) -> Response:
        try:
            clamp_body_size(req.body, max_bytes=MAX_BODY_BYTES)
            if req.body:
                import json
                req.json_body = json.loads(req.body.decode("utf-8"))
        except (ValidationError, ValueError) as exc:
            return Response(status=400, body={"error": "invalid_request", "detail": str(exc)})
        return with_envelope(req)

    def with_envelope(req: Request) -> Response:
        """Open the sealed request body, and seal the reply symmetrically.

        The envelope is MANDATORY for any request carrying a body. A body
        that is not an envelope, or that is one but does not open, is
        rejected outright — a wrong key, a tampered packet, or a plaintext
        client cannot degrade the channel.

        Bodyless requests (GET, health checks) have nothing to seal and pass
        through; their replies are sealed only when a channel key exists.
        """
        api_key = config.api_key or ""
        has_body = req.json_body is not None

        if has_body:
            if not is_envelope(req.json_body):
                log_security_event(
                    logger, "plaintext_body_rejected", "high", {"path": req.path}
                )
                return Response(status=400, body={"error": "envelope_required"})
            try:
                req.json_body = unseal(req.json_body, api_key)
            except EnvelopeError as exc:
                log_security_event(
                    logger, "envelope_open_failure", "high", {"path": req.path, "reason": str(exc)}
                )
                return Response(status=400, body={"error": "invalid_envelope"})

        response = with_auth(req)

        if api_key:
            try:
                response.body = seal(response.body, api_key)
            except EnvelopeError as exc:
                logger.error("envelope seal failed", path=req.path, error=str(exc))
                return Response(status=500, body={"error": "internal_error"})
        return response

    def with_rate_limit(req: Request) -> Response:
        key = req.headers.get("authorization", req.remote_addr)
        if not rate_limiter.allow(key):
            log_security_event(logger, "rate_limited", "low", {"path": req.path, "key_hash": hash(key)})
            return Response(status=429, body={"error": "rate_limited"})
        return with_validation(req)

    def with_logging(req: Request) -> Response:
        start = time.monotonic()
        response = with_rate_limit(req)
        duration_ms = (time.monotonic() - start) * 1000
        log_request(logger, req.method, req.path, response.status, duration_ms, req.principal)
        return response

    def with_security_headers(req: Request) -> Response:
        response = with_logging(req)
        response.headers.update(security_headers())
        response.body = sanitize_output(response.body)
        return response

    def with_error_handling(req: Request) -> Response:
        try:
            return with_security_headers(req)
        except Exception as exc:  # noqa: BLE001 - last line of defense
            logger.error("unhandled error", path=req.path, error=str(exc))
            return Response(
                status=500,
                body={"error": "internal_error", "request_id": req.request_id, "timestamp": now_iso()},
                headers=security_headers(),
            )

    return with_error_handling


def serialize_response(response: Response) -> bytes:
    return to_json_bytes(response.body)
