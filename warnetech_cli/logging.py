"""
Structured Logging Module
Implements JSON-based structured logging for all CLI operations.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """Format log messages as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data, default=str)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    structured: bool = True,
) -> logging.Logger:
    """
    Configure structured logging for warnetech CLI.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        structured: Use structured JSON logging

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("warnetech")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if requested
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def log_operation(
    logger: logging.Logger,
    operation: str,
    status: str,
    duration_ms: float = 0,
    **kwargs: Any,
) -> None:
    """
    Log a structured operation event.

    Args:
        logger: Logger instance
        operation: Operation name
        status: Status (success, failure, started)
        duration_ms: Duration in milliseconds
        **kwargs: Additional data to include
    """
    extra_data = {
        "operation": operation,
        "status": status,
        "duration_ms": duration_ms,
        **kwargs,
    }

    if hasattr(logger, "_log"):
        # Access internal _log to attach extra_data
        record = logger.makeRecord(
            logger.name,
            logging.INFO,
            "", 0, f"Operation: {operation} - {status}",
            (), None,
        )
        record.extra_data = extra_data
        logger.handle(record)
    else:
        logger.info(f"Operation: {operation} - {status} | {json.dumps(extra_data)}")
