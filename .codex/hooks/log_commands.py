#!/usr/bin/env python3
"""PreToolUse hook (Bash): append every shell command to a JSONL log.

Log lines: {"ts": iso8601, "command": str, "description": str}
Location: .claude/hooks/command_log.jsonl (gitignored). Never blocks (exit 0).
"""

import json
import os
import sys
from datetime import datetime, timezone


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    log_path = os.path.join(project_dir, ".claude", "hooks", "command_log.jsonl")
    line = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "command": str(tool_input.get("command", "")),
        "description": str(tool_input.get("description", "")),
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
