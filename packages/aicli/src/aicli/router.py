"""Routing: turn a model string into a provider call, with logged fallback.

Phase 1 routing is deliberately dumb and visible: try the requested model, then
each entry in ``fallback`` in order, and record every hop. Cost- and
latency-aware routing is Phase 2; it needs this audit trail to be trustworthy
first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config, ConfigError
from .providers import Completion, Message, Provider, ProviderError, build

# Bare model names that unambiguously belong to one provider type.
_PREFIX_TO_TYPE = (("claude-", "anthropic"), ("gpt-", "openai"), ("o1", "openai"),
                   ("o3", "openai"), ("o4", "openai"))


@dataclass(frozen=True)
class Target:
    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass
class RouteResult:
    completion: Completion
    target: Target
    attempts: list[tuple[Target, str]] = field(default_factory=list)  # failed hops

    @property
    def fell_back_from(self) -> Target | None:
        return self.attempts[0][0] if self.attempts else None


class AllProvidersFailed(Exception):
    def __init__(self, attempts: list[tuple[Target, str]]):
        self.attempts = attempts
        lines = "\n".join(f"  {t}: {why}" for t, why in attempts)
        super().__init__(f"every candidate failed:\n{lines}")


class Router:
    def __init__(self, config: Config):
        self.config = config
        self._providers: dict[str, Provider] = {}

    def provider(self, name: str) -> Provider:
        if name not in self._providers:
            if name not in self.config.providers:
                raise ConfigError(
                    f"no provider named {name!r} (configured: {', '.join(self.config.providers)})"
                )
            self._providers[name] = build(self.config.providers[name])
        return self._providers[name]

    def resolve(self, model: str | None) -> Target:
        """``provider/model``, an alias, or a bare name with an obvious owner."""
        spec = model or self.config.default_model
        spec = self.config.aliases.get(spec, spec)
        if "/" in spec:
            head, rest = spec.split("/", 1)
            if head in self.config.providers:
                return Target(head, rest)
        for prefix, ptype in _PREFIX_TO_TYPE:
            if spec.startswith(prefix):
                for name, pcfg in self.config.providers.items():
                    if pcfg.type == ptype:
                        return Target(name, spec)
        raise ConfigError(
            f"cannot tell which provider serves {spec!r}; use provider/model, "
            f"e.g. local/{spec}, or add an alias"
        )

    def candidates(self, model: str | None) -> list[Target]:
        chain = [self.resolve(model)]
        for spec in self.config.fallback:
            target = self.resolve(spec)
            if target not in chain:
                chain.append(target)
        return chain

    def provider_type(self, target: Target) -> str:
        return self.config.providers[target.provider].type

    def complete(self, messages: list[Message], model: str | None = None,
                 max_tokens: int | None = None, system: str | None = None,
                 on_fallback=None) -> RouteResult:
        attempts: list[tuple[Target, str]] = []
        for target in self.candidates(model):
            try:
                completion = self.provider(target.provider).complete(
                    messages, target.model, max_tokens or self.config.max_tokens, system
                )
            except ProviderError as exc:
                attempts.append((target, str(exc)))
                if on_fallback:
                    on_fallback(target, str(exc))
                continue
            return RouteResult(completion, target, attempts)
        raise AllProvidersFailed(attempts)
