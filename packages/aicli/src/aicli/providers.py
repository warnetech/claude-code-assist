"""Providers: the only code that talks to a model.

Each provider is a thin HTTP client over the vendor's own API, written against
urllib so Phase 1 installs with no dependencies. Everything above this module
sees one shape: ``complete(messages, model, max_tokens) -> Completion``.

A provider raises ``ProviderError`` for anything that should trigger fallback
(unreachable, missing key, 5xx, 429, refusal) — the router decides what to do.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import ConfigError, ProviderConfig
from .pricing import estimate_tokens

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT = 120.0
HEALTH_TIMEOUT = 2.0

Message = dict[str, str]  # {"role": "user" | "assistant", "content": str}


class ProviderError(Exception):
    """A call failed in a way the router may recover from by falling back."""


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None
    latency_ms: int


def _http(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("content-type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise ProviderError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"cannot reach {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProviderError(f"non-JSON response from {url}") from exc


class Provider:
    type = "base"

    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self.name = cfg.name

    def complete(self, messages: list[Message], model: str, max_tokens: int,
                 system: str | None = None) -> Completion:
        raise NotImplementedError

    def available(self) -> tuple[bool, str]:
        """Cheap readiness check. Never raises; the reason is shown to the user."""
        raise NotImplementedError

    def list_models(self) -> list[str]:
        return []

    def _require_key(self) -> str:
        key = self.cfg.api_key()
        if not key:
            raise ProviderError(f"{self.name}: ${self.cfg.api_key_env} is not set")
        return key


class AnthropicProvider(Provider):
    type = "anthropic"

    @property
    def base(self) -> str:
        return (self.cfg.base_url or "https://api.anthropic.com").rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._require_key(), "anthropic-version": ANTHROPIC_VERSION}

    def complete(self, messages, model, max_tokens, system=None):
        body: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            body["system"] = system
        start = time.monotonic()
        data = _http("POST", f"{self.base}/v1/messages", body, self._headers())
        stop = data.get("stop_reason")
        # A refusal is HTTP 200 with no text: surface it instead of printing "".
        if stop == "refusal":
            raise ProviderError(f"{self.name}: model refused the request")
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        return Completion(
            text=text, provider=self.name, model=data.get("model", model),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            stop_reason=stop, latency_ms=int((time.monotonic() - start) * 1000),
        )

    def available(self):
        if not self.cfg.api_key():
            return False, f"${self.cfg.api_key_env} not set"
        return True, "API key present"

    def list_models(self):
        data = _http("GET", f"{self.base}/v1/models?limit=100", headers=self._headers(),
                     timeout=HEALTH_TIMEOUT * 5)
        return [m["id"] for m in data.get("data", [])]


class OpenAIProvider(Provider):
    """OpenAI, or anything that speaks its chat-completions API (set base_url)."""

    type = "openai"

    @property
    def base(self) -> str:
        return (self.cfg.base_url or "https://api.openai.com/v1").rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self._require_key()}"}

    def complete(self, messages, model, max_tokens, system=None):
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        body = {"model": model, "messages": msgs, "max_completion_tokens": max_tokens}
        start = time.monotonic()
        data = _http("POST", f"{self.base}/chat/completions", body, self._headers())
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage", {})
        return Completion(
            text=(choice.get("message") or {}).get("content") or "",
            provider=self.name, model=data.get("model", model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=choice.get("finish_reason"),
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def available(self):
        if not self.cfg.api_key():
            return False, f"${self.cfg.api_key_env} not set"
        return True, "API key present"

    def list_models(self):
        data = _http("GET", f"{self.base}/models", headers=self._headers(),
                     timeout=HEALTH_TIMEOUT * 5)
        return sorted(m["id"] for m in data.get("data", []))


class OllamaProvider(Provider):
    type = "ollama"

    @property
    def base(self) -> str:
        return (self.cfg.base_url or "http://localhost:11434").rstrip("/")

    def complete(self, messages, model, max_tokens, system=None):
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        body = {"model": model, "messages": msgs, "stream": False,
                "options": {"num_predict": max_tokens}}
        start = time.monotonic()
        data = _http("POST", f"{self.base}/api/chat", body)
        return Completion(
            text=(data.get("message") or {}).get("content", ""),
            provider=self.name, model=data.get("model", model),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            stop_reason=data.get("done_reason"),
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def available(self):
        try:
            _http("GET", f"{self.base}/api/tags", timeout=HEALTH_TIMEOUT)
        except ProviderError as exc:
            return False, f"Ollama not reachable at {self.base} ({exc.__cause__ or exc})"
        return True, f"Ollama running at {self.base}"

    def list_models(self):
        data = _http("GET", f"{self.base}/api/tags", timeout=HEALTH_TIMEOUT)
        return [m["name"] for m in data.get("models", [])]


class FakeProvider(Provider):
    """Offline echo. ``fail = true`` in its config makes it fail, to exercise fallback."""

    type = "fake"

    def complete(self, messages, model, max_tokens, system=None):
        if self.cfg.options.get("fail"):
            raise ProviderError(f"{self.name}: configured to fail")
        prompt = messages[-1]["content"] if messages else ""
        text = f"echo: {prompt}"
        return Completion(
            text=text, provider=self.name, model=model,
            input_tokens=estimate_tokens("".join(m["content"] for m in messages)),
            output_tokens=estimate_tokens(text), stop_reason="end_turn", latency_ms=0,
        )

    def available(self):
        if self.cfg.options.get("fail"):
            return False, "configured to fail"
        return True, "offline echo provider"

    def list_models(self):
        return ["echo"]


PROVIDER_TYPES: dict[str, type[Provider]] = {
    cls.type: cls for cls in (AnthropicProvider, OpenAIProvider, OllamaProvider, FakeProvider)
}


def build(cfg: ProviderConfig) -> Provider:
    try:
        return PROVIDER_TYPES[cfg.type](cfg)
    except KeyError:
        raise ConfigError(
            f"provider {cfg.name!r}: unknown type {cfg.type!r} "
            f"(expected one of {sorted(PROVIDER_TYPES)})"
        ) from None
