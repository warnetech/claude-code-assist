"""Structured logging for all migration operations.

Named ``logging.py`` inside the package but never shadows the stdlib
module for other code — same mechanism as every other package's
logging.py in this repo, intentionally duplicated rather than shared.
"""

from __future__ import annotations

import json
import logging as _stdlib_logging
import sys
import time
from typing import Any


class _JsonFormatter(_stdlib_logging.Formatter):
    def format(self, record: _stdlib_logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class SchemaLoggerAdapter(_stdlib_logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra_fields = {k: v for k, v in kwargs.items() if k not in ("exc_info", "stack_info", "stacklevel")}
        for key in extra_fields:
            kwargs.pop(key)
        kwargs["extra"] = {"extra_fields": extra_fields}
        return msg, kwargs


_CONFIGURED_LOGGERS: set[str] = set()


def get_logger(name: str, level: int = _stdlib_logging.INFO) -> SchemaLoggerAdapter:
    base = _stdlib_logging.getLogger(f"warnetech.supabase_schema.{name}")
    if name not in _CONFIGURED_LOGGERS:
        base.setLevel(level)
        handler = _stdlib_logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(_JsonFormatter())
        base.addHandler(handler)
        base.propagate = False
        _CONFIGURED_LOGGERS.add(name)
    return SchemaLoggerAdapter(base, {})


def log_migration_step(logger: SchemaLoggerAdapter, step: str, status: str, detail: dict | None = None) -> None:
    logger.info("migration_step", step=step, status=status, detail=detail or {})
