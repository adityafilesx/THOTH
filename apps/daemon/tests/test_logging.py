import json
import logging
from pathlib import Path

from thoth_daemon.logging_setup import configure_logging, get_logger


def read_lines(log_dir: Path) -> list[dict[str, object]]:
    files = sorted(log_dir.glob("*.jsonl"))
    assert files, f"no jsonl log files in {log_dir}"
    lines: list[dict[str, object]] = []
    for f in files:
        for raw in f.read_text().splitlines():
            lines.append(json.loads(raw))
    return lines


def test_jsonl_lines_are_structured(tmp_path: Path) -> None:
    configure_logging(tmp_path, "INFO")
    log = get_logger("thoth.test")
    log.info("task_created", extra={"data": {"task_id": "t1"}})
    logging.shutdown()
    lines = read_lines(tmp_path)
    line = next(ln for ln in lines if ln.get("event") == "task_created")
    assert line["level"] == "INFO"
    assert line["logger"] == "thoth.test"
    assert isinstance(line["ts"], str)
    assert line["data"] == {"task_id": "t1"}


def test_log_redaction(tmp_path: Path) -> None:
    configure_logging(tmp_path, "INFO")
    log = get_logger("thoth.test.redact")
    log.info("tool_result", extra={"data": {"api_key": "sk-123", "safe": "y"}})
    logging.shutdown()
    lines = read_lines(tmp_path)
    line = next(ln for ln in lines if ln.get("event") == "tool_result")
    data = line["data"]
    assert isinstance(data, dict)
    assert data["api_key"] == "[REDACTED]"
    assert data["safe"] == "y"
