"""Structured logging for all connector operations: requests made,
responses received, errors, and data pushed to the control plane or
database.

Named ``logging.py`` inside the package but never shadows the stdlib
module for other code — same mechanism as the other three packages'
logging.py, intentionally duplicated rather than shared.
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


class ConnectorLoggerAdapter(_stdlib_logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra_fields = {k: v for k, v in kwargs.items() if k not in ("exc_info", "stack_info", "stacklevel")}
        for key in extra_fields:
            kwargs.pop(key)
        kwargs["extra"] = {"extra_fields": extra_fields}
        return msg, kwargs


_CONFIGURED_LOGGERS: set[str] = set()


def get_logger(name: str, level: int = _stdlib_logging.INFO) -> ConnectorLoggerAdapter:
    base = _stdlib_logging.getLogger(f"warnetech.connectors.{name}")
    if name not in _CONFIGURED_LOGGERS:
        base.setLevel(level)
        handler = _stdlib_logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(_JsonFormatter())
        base.addHandler(handler)
        base.propagate = False
        _CONFIGURED_LOGGERS.add(name)
    return ConnectorLoggerAdapter(base, {})


# -- specialized event loggers -------------------------------------------------


def log_request(logger: ConnectorLoggerAdapter, connector: str, method: str, target: str) -> None:
    logger.info("connector_request", connector=connector, method=method, target=target)


def log_response(logger: ConnectorLoggerAdapter, connector: str, ok: bool, duration_ms: float, status: int | None = None) -> None:
    logger.info("connector_response", connector=connector, ok=ok, duration_ms=duration_ms, status=status)


def log_error(logger: ConnectorLoggerAdapter, connector: str, error: str) -> None:
    logger.error("connector_error", connector=connector, error=error)


def log_push_to_control_plane(logger: ConnectorLoggerAdapter, connector: str, record_count: int) -> None:
    logger.info("push_to_control_plane", connector=connector, record_count=record_count)


def log_push_to_database(logger: ConnectorLoggerAdapter, connector: str, table: str, record_count: int) -> None:
    logger.info("push_to_database", connector=connector, table=table, record_count=record_count)
