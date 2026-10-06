"""Structured JSON logging with automatic redaction of sensitive fields."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

_SENSITIVE = re.compile(r"(password|passwd|secret|token|authorization|encryption_key|api_key|private)", re.I)
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _RESERVED:
                data[k] = "[REDACTED]" if _SENSITIVE.search(k) else v
        if record.exc_info and record.exc_info[0]:
            data["exc_type"] = record.exc_info[0].__name__  # type only; messages may hold secrets
        return json.dumps(data, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("cyart")
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"cyart.{name}")


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Log `event` with structured fields. Sensitive-looking field names are redacted."""
    safe = {k: ("[REDACTED]" if _SENSITIVE.search(k) else v) for k, v in fields.items()}
    logger.log(level, event, extra=safe)
