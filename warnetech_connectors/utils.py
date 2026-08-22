"""Helper functions: HTTP requests, JSON handling, backoff and retry, and
timestamp formatting.

HTTP uses only the standard library (urllib), consistent with every other
package in this system. `request_with_retry` is the one piece of shared
plumbing every connector module builds on — it centralizes backoff so no
individual connector reimplements it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Optional


# -- timestamps -----------------------------------------------------------------


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def format_timestamp(epoch_seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_seconds))


# -- JSON -----------------------------------------------------------------------


def to_json(obj: Any) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"))


def from_json(text: str) -> Any:
    return json.loads(text) if text else None


# -- HTTP -----------------------------------------------------------------------


class HttpResult:
    def __init__(self, ok: bool, status: Optional[int] = None, body: Any = None, error: Optional[str] = None) -> None:
        self.ok = ok
        self.status = status
        self.body = body
        self.error = error

    def to_dict(self) -> dict:
        return {"ok": self.ok, "status": self.status, "body": self.body, "error": self.error}


def http_request(method: str, url: str, headers: Optional[dict] = None, body: Optional[Any] = None, timeout: float = 10.0) -> HttpResult:
    data = to_json(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    if data is not None and "Content-Type" not in (headers or {}):
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return HttpResult(ok=True, status=resp.status, body=from_json(raw.decode("utf-8")) if raw else None)
    except urllib.error.HTTPError as exc:
        try:
            detail = from_json(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = None
        return HttpResult(ok=False, status=exc.code, body=detail, error=f"HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return HttpResult(ok=False, error=str(exc.reason))
    except TimeoutError:
        return HttpResult(ok=False, error="request timed out")


# -- backoff / retry --------------------------------------------------------------


def request_with_retry(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    body: Optional[Any] = None,
    timeout: float = 10.0,
    max_retries: int = 3,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 30.0,
    sleep_fn=time.sleep,
) -> HttpResult:
    """Retries only on transport-level failure or a 5xx/429 response —
    never on 4xx client errors (a malformed request will not fix itself by
    waiting). Backoff doubles each attempt, capped at `max_delay_seconds`.
    """
    attempt = 0
    delay = base_delay_seconds
    result = HttpResult(ok=False, error="no attempt made")

    while attempt <= max_retries:
        result = http_request(method, url, headers=headers, body=body, timeout=timeout)
        if result.ok:
            return result
        if result.status is not None and result.status not in (429, 500, 502, 503, 504):
            return result  # client error: retrying will not help

        attempt += 1
        if attempt > max_retries:
            break
        sleep_fn(min(delay, max_delay_seconds))
        delay *= 2

    return result
