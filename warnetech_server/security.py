"""Core security mechanisms: input validation, output sanitization, request
signing, response integrity checks, and defense-in-depth helpers.

These are building blocks middleware.py and routes.py compose — this module
performs no I/O and holds no server state, so it can be unit tested in
isolation.
"""

from __future__ import annotations

import hmac
import re
import time
from hashlib import sha256
from typing import Any

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ValidationError(ValueError):
    pass


# -- input validation -------------------------------------------------------------


def validate_string(value: Any, *, field: str, max_length: int = 4096, allow_empty: bool = False, pattern: str | None = None) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    if not allow_empty and not value.strip():
        raise ValidationError(f"{field} must not be empty")
    if len(value) > max_length:
        raise ValidationError(f"{field} exceeds max length {max_length}")
    if pattern and not re.match(pattern, value):
        raise ValidationError(f"{field} does not match required pattern")
    return value


def validate_json_body(body: Any, *, required_fields: tuple[str, ...] = ()) -> dict:
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    missing = [f for f in required_fields if f not in body]
    if missing:
        raise ValidationError(f"missing required field(s): {', '.join(missing)}")
    return body


def guard_path_traversal(path_segment: str, *, field: str = "path") -> str:
    if ".." in path_segment or path_segment.startswith("/") or "\\" in path_segment:
        raise ValidationError(f"{field} contains an invalid path segment")
    return path_segment


# -- output sanitization -----------------------------------------------------------


def sanitize_output(obj: Any) -> Any:
    """Recursively strips control characters from string values so nothing
    a downstream consumer (log viewer, terminal, browser) treats specially
    can leak through an API response unescaped.
    """
    if isinstance(obj, str):
        return _CONTROL_CHARS.sub("", obj)
    if isinstance(obj, dict):
        return {k: sanitize_output(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_output(v) for v in obj]
    return obj


# -- request signing / integrity -----------------------------------------------------


def sign_request(secret: str, method: str, path: str, body: bytes, timestamp: int | None = None) -> tuple[str, int]:
    timestamp = timestamp if timestamp is not None else int(time.time())
    message = f"{method.upper()}\n{path}\n{timestamp}\n".encode("utf-8") + body
    signature = hmac.new(secret.encode("utf-8"), message, sha256).hexdigest()
    return signature, timestamp


def verify_signature(secret: str, signature: str, method: str, path: str, body: bytes, timestamp: int, max_skew_seconds: int = 300) -> bool:
    if abs(int(time.time()) - timestamp) > max_skew_seconds:
        return False
    expected, _ = sign_request(secret, method, path, body, timestamp)
    return constant_time_compare(expected, signature)


def response_checksum(body: bytes) -> str:
    return sha256(body).hexdigest()


def verify_response_checksum(body: bytes, expected: str) -> bool:
    return constant_time_compare(response_checksum(body), expected)


# -- defense-in-depth ---------------------------------------------------------------


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def clamp_body_size(body: bytes, *, max_bytes: int) -> bytes:
    if len(body) > max_bytes:
        raise ValidationError(f"request body exceeds {max_bytes} bytes")
    return body
