"""API key authentication and optional token-based authentication.

Fails closed: if `config.api_key` is unset, every request is rejected
rather than the older `warnetech-server`'s `isAuthorized()` which returned
`true` when `API_KEY` was unset. A quota or config problem must never
become a security hole.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Optional

from .config import ServerConfig
from .security import constant_time_compare


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    principal: Optional[str] = None
    reason: Optional[str] = None


def authenticate(config: ServerConfig, headers: dict) -> AuthResult:
    if not config.api_key:
        return AuthResult(ok=False, reason="server has no API_KEY configured; refusing all requests")

    auth_header = headers.get("authorization") or headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        token_header = headers.get("x-auth-token") or headers.get("X-Auth-Token")
        if token_header and config.auth_token_secret:
            return _authenticate_token(config, token_header)
        return AuthResult(ok=False, reason="missing Authorization: Bearer header")

    presented = auth_header[len("Bearer "):]
    if constant_time_compare(presented, config.api_key):
        return AuthResult(ok=True, principal="api_key")
    return AuthResult(ok=False, reason="invalid API key")


# -- optional token-based auth -----------------------------------------------------
# A minimal signed-token scheme: base64("<principal>:<expiry_epoch>:<hmac>").
# Intended for short-lived, revocable tokens issued to trusted internal
# callers (e.g. the CLI) without handing out the long-lived API key.


def issue_token(config: ServerConfig, principal: str, ttl_seconds: int = 3600) -> str:
    if not config.auth_token_secret:
        raise ValueError("auth_token_secret is not configured; cannot issue tokens")
    import hmac
    from hashlib import sha256

    expiry = int(time.time()) + ttl_seconds
    payload = f"{principal}:{expiry}"
    signature = hmac.new(config.auth_token_secret.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()
    raw = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _authenticate_token(config: ServerConfig, token: str) -> AuthResult:
    import hmac
    from hashlib import sha256

    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        principal, expiry_str, signature = raw.rsplit(":", 2)
        expiry = int(expiry_str)
    except (ValueError, UnicodeDecodeError):
        return AuthResult(ok=False, reason="malformed token")

    if time.time() > expiry:
        return AuthResult(ok=False, reason="token expired")

    payload = f"{principal}:{expiry}"
    expected = hmac.new(config.auth_token_secret.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()
    if not constant_time_compare(expected, signature):
        return AuthResult(ok=False, reason="invalid token signature")

    return AuthResult(ok=True, principal=principal)
