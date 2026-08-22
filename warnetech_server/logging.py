"""Structured logging for all server operations: request logs, security
events, test runs, AI interactions, control-plane calls, and database
operations.

Named ``logging.py`` inside the package but never shadows the stdlib
module for other code — see warnetech_control_plane/logging.py for the
same note; the mechanism here is identical and intentionally duplicated
rather than shared, since these are two independently deployable packages.
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


class ServerLoggerAdapter(_stdlib_logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra_fields = {k: v for k, v in kwargs.items() if k not in ("exc_info", "stack_info", "stacklevel")}
        for key in extra_fields:
            kwargs.pop(key)
        kwargs["extra"] = {"extra_fields": extra_fields}
        return msg, kwargs


_CONFIGURED_LOGGERS: set[str] = set()


def get_logger(name: str, level: int = _stdlib_logging.INFO) -> ServerLoggerAdapter:
    base = _stdlib_logging.getLogger(f"warnetech.server.{name}")
    if name not in _CONFIGURED_LOGGERS:
        base.setLevel(level)
        handler = _stdlib_logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(_JsonFormatter())
        base.addHandler(handler)
        base.propagate = False
        _CONFIGURED_LOGGERS.add(name)
    return ServerLoggerAdapter(base, {})


# -- specialized event loggers -------------------------------------------------
# Thin wrappers so callers don't repeat the same `extra_fields` shape at every
# call site; each still goes through the same JSON formatter above.


def log_request(logger: ServerLoggerAdapter, method: str, path: str, status: int, duration_ms: float, principal: str | None) -> None:
    logger.info("request", method=method, path=path, status=status, duration_ms=duration_ms, principal=principal)


def log_security_event(logger: ServerLoggerAdapter, event_type: str, severity: str, detail: dict) -> None:
    logger.warning("security_event", event_type=event_type, severity=severity, detail=detail)


def log_test_run(logger: ServerLoggerAdapter, test_id: str, scenario: str, status: str, duration_ms: float) -> None:
    logger.info("test_run", test_id=test_id, scenario=scenario, status=status, duration_ms=duration_ms)


def log_ai_interaction(logger: ServerLoggerAdapter, operation: str, ok: bool, detail: dict) -> None:
    logger.info("ai_interaction", operation=operation, ok=ok, detail=detail)


def log_control_plane_call(logger: ServerLoggerAdapter, operation: str, ok: bool, duration_ms: float) -> None:
    logger.info("control_plane_call", operation=operation, ok=ok, duration_ms=duration_ms)


def log_database_operation(logger: ServerLoggerAdapter, operation: str, table: str, ok: bool) -> None:
    logger.info("database_operation", operation=operation, table=table, ok=ok)
