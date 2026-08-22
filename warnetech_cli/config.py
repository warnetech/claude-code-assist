"""
Configuration Management Module
Handles loading, saving, and validating warnetech CLI configuration.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse


class Config:
    """Configuration management for warnetech CLI."""

    DEFAULT_CONFIG_DIR = Path.home() / ".warnetech"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"

    REQUIRED_KEYS = [
        "server_url",
        "api_key",
        "supabase_url",
        "supabase_key",
    ]

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config file (default: ~/.warnetech/config.json)
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_FILE
        self.data: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not self.config_path.exists():
            return self._get_defaults()

        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            return config
        except (json.JSONDecodeError, IOError) as e:
            raise RuntimeError(f"Failed to load config: {e}")

    def _get_defaults(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "server_url": os.getenv("WARNETECH_SERVER_URL", "http://localhost:8080"),
            "api_key": os.getenv("WARNETECH_API_KEY", ""),
            "supabase_url": os.getenv("SUPABASE_URL", ""),
            "supabase_key": os.getenv("SUPABASE_KEY", ""),
            "ai_fallback_url": os.getenv("AI_FALLBACK_URL", ""),
            "ai_fallback_key": os.getenv("AI_FALLBACK_KEY", ""),
            "retention_hot_days": 3,
            "retention_warm_days": 30,
            "retention_ghost_years": 1,
            "compression_hot": "lz4",
            "compression_warm": "zstd-medium",
            "compression_ghost": "zstd-max",
            "log_level": "INFO",
            "backup_dir": str(Path.home() / ".warnetech" / "backups"),
            "cache_dir": str(Path.home() / ".warnetech" / "cache"),
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self.data[key] = value

    LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})

    def validate(self) -> bool:
        """Validate required configuration."""
        missing = [k for k in self.REQUIRED_KEYS if not self.get(k)]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
        self.validate_server_url(self.get("server_url"))
        return True

    @classmethod
    def validate_server_url(cls, url: Optional[str]) -> str:
        """Require https:// for any non-loopback server_url.

        Request bodies are sealed in the canonical AES-256-GCM envelope, but
        the Bearer API key rides in a plaintext header, so plain HTTP to a
        remote host would still leak it. Loopback is exempt so local
        development against http://localhost:8080 keeps working.
        """
        if not url:
            return ""

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"server_url must be http:// or https://, got {parsed.scheme or 'no'} scheme")

        if parsed.scheme == "https":
            return url

        if (parsed.hostname or "") in cls.LOCAL_HOSTS:
            return url

        raise ValueError(
            f"server_url must use https:// for non-local hosts (got {url}). "
            "Plain HTTP would expose the Bearer API key in transit."
        )

    def save(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.data, f, indent=2)
        # Set restrictive permissions for security
        os.chmod(self.config_path, 0o600)

    def to_dict(self) -> Dict[str, Any]:
        """Get configuration as dictionary (excluding secrets)."""
        safe_config = {k: v for k, v in self.data.items() if "key" not in k.lower()}
        safe_config["server_url"] = self.get("server_url")
        safe_config["supabase_url"] = self.get("supabase_url")
        return safe_config
