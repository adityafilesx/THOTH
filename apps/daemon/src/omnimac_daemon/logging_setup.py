"""Structured JSONL logging with redaction at write time.

Usage:
    configure_logging(log_dir, "INFO")
    log = get_logger("omnimac.orchestrator")
    log.info("task_created", extra={"data": {"task_id": "..."}})

Each line: {"ts", "level", "logger", "event", ...data}. The ``data`` dict is
redacted before serialization (see security/redaction.py).
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omnimac_daemon.security.redaction import redact

_LOGGER_PREFIX = "omnimac"


class JsonlFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        data = getattr(record, "data", None)
        if isinstance(data, dict):
            line["data"] = redact(data)
        if record.exc_info and record.exc_info[0] is not None:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False, default=str)


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / f"omnimac-{datetime.now(UTC).strftime('%Y%m%d')}.jsonl"

    root = logging.getLogger(_LOGGER_PREFIX)
    root.setLevel(level.upper())
    # Reconfiguration (tests, restarts): drop stale handlers.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    file_handler = logging.FileHandler(logfile, encoding="utf-8")
    file_handler.setFormatter(JsonlFormatter())
    root.addHandler(file_handler)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    if not name.startswith(_LOGGER_PREFIX):
        name = f"{_LOGGER_PREFIX}.{name}"
    return logging.getLogger(name)
