"""Configuration: one TOML file, with defaults that work before it exists.

API keys are never written to the config. A provider names the environment
variable that holds its key (``api_key_env``), so the file is safe to commit or
paste into an issue.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = """\
# aicli configuration. Keys are read from the environment, never stored here.

# Local-first: the default model runs on your machine via Ollama.
default_model = "local/llama3.2"

# Tried in order when the requested model's provider fails. Empty means
# "never silently send my prompt somewhere else". Add cloud models here only
# if you are happy for a local failure to go to the cloud.
fallback = []

format = "text"        # text | json | markdown
max_tokens = 1024

[providers.local]
type = "ollama"
base_url = "http://localhost:11434"

[providers.anthropic]
type = "anthropic"
api_key_env = "ANTHROPIC_API_KEY"

[providers.openai]
type = "openai"
api_key_env = "OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"

# Offline echo provider: try aicli with no keys and no Ollama.
[providers.echo]
type = "fake"

[aliases]
opus = "anthropic/claude-opus-5"
sonnet = "anthropic/claude-sonnet-5"
haiku = "anthropic/claude-haiku-4-5"
gpt-4o = "openai/gpt-4o"
mistral = "local/mistral"

# Override or add prices, USD per 1M tokens: model = [input, output]
[prices]
"""

VALID_FORMATS = ("text", "json", "markdown")


class ConfigError(Exception):
    """The config file is missing something or contradicts itself."""


@dataclass
class ProviderConfig:
    name: str
    type: str
    base_url: str | None = None
    api_key_env: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None


@dataclass
class Config:
    default_model: str
    fallback: list[str]
    format: str
    max_tokens: int
    providers: dict[str, ProviderConfig]
    aliases: dict[str, str]
    prices: dict[str, tuple[float, float]]
    path: Path | None = None


def home() -> Path:
    """Where config and history live. ``AICLI_HOME`` overrides, for tests and CI."""
    return Path(os.environ.get("AICLI_HOME") or Path.home() / ".aicli")


def config_path() -> Path:
    return home() / "config.toml"


def parse(text: str, path: Path | None = None) -> Config:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path or 'config'}: {exc}") from exc

    providers: dict[str, ProviderConfig] = {}
    for name, spec in raw.get("providers", {}).items():
        if "type" not in spec:
            raise ConfigError(f"provider {name!r} has no type")
        known = {"type", "base_url", "api_key_env"}
        providers[name] = ProviderConfig(
            name=name,
            type=spec["type"],
            base_url=spec.get("base_url"),
            api_key_env=spec.get("api_key_env"),
            options={k: v for k, v in spec.items() if k not in known},
        )

    fmt = raw.get("format", "text")
    if fmt not in VALID_FORMATS:
        raise ConfigError(f"format must be one of {VALID_FORMATS}, got {fmt!r}")

    prices = {}
    for model, pair in raw.get("prices", {}).items():
        if not (isinstance(pair, list) and len(pair) == 2):
            raise ConfigError(f"price for {model!r} must be [input, output]")
        prices[model] = (float(pair[0]), float(pair[1]))

    return Config(
        default_model=raw.get("default_model", "local/llama3.2"),
        fallback=list(raw.get("fallback", [])),
        format=fmt,
        max_tokens=int(raw.get("max_tokens", 1024)),
        providers=providers,
        aliases=dict(raw.get("aliases", {})),
        prices=prices,
        path=path,
    )


def load(path: Path | None = None) -> Config:
    """Load the config file, or the built-in defaults if there is none yet."""
    path = path or config_path()
    if path.exists():
        return parse(path.read_text(encoding="utf-8"), path)
    return parse(DEFAULT_CONFIG)


def init(path: Path | None = None, force: bool = False) -> Path:
    path = path or config_path()
    if path.exists() and not force:
        raise ConfigError(f"{path} already exists (use --force to overwrite)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return path
