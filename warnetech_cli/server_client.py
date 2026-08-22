"""HTTP client for warnetech-server.

Wraps the routes warnetech_cli actually calls, using only the standard
library (urllib) — consistent with how warnetech_server itself talks to
Supabase. Every call fails soft: on error it returns
``{"error": "..."}`` rather than raising, so a command can report a clean
failure instead of an unhandled traceback.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

from warnetech_cli.config import Config
from warnetech_envelope import EnvelopeError, is_envelope, seal, unseal


class ServerClient:
    def __init__(self, config: Config) -> None:
        self._base_url = (config.get("server_url") or "").rstrip("/")
        self._api_key = config.get("api_key") or ""
        self._timeout = 10

    def _request(self, method: str, path: str, params: Optional[dict] = None, body: Optional[Any] = None) -> dict:
        if not self._base_url:
            return {"error": "server_url is not configured"}
        if not self._api_key:
            # The envelope is mandatory, and the API key is the channel key.
            # Without one there is nothing to seal with, so refuse rather
            # than silently downgrade to plaintext.
            return {"error": "api_key is not configured; the encrypted channel requires one"}

        url = f"{self._base_url}/{path.lstrip('/')}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            if query:
                url = f"{url}?{query}"

        if body is not None:
            body = seal(body, self._api_key)

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self._api_key}")
        req.add_header("X-Warnetech-Envelope", "aes-256-gcm")

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                return self._open(json.loads(raw)) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                detail = self._open(json.loads(exc.read()))
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = exc.reason
            return {"error": f"server returned {exc.code}", "detail": detail}
        except urllib.error.URLError as exc:
            return {"error": "server unreachable", "reason": str(exc.reason)}

    def _open(self, payload: Any) -> Any:
        """Unseal a response if it arrived sealed; pass it through if not."""
        if not is_envelope(payload):
            return payload
        try:
            return unseal(payload, self._api_key)
        except EnvelopeError as exc:
            return {"error": "response decryption failed", "reason": str(exc)}

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: Optional[Any] = None) -> dict:
        return self._request("POST", path, body=body)
