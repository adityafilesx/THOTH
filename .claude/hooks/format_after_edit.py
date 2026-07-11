#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write): format the edited file.

Python files -> ruff format (via uv). TS/TSX/JS/CSS/JSON/MD -> prettier (via
pnpm exec, if installed). Best-effort: formatting failures never block (exit 0).
"""

import json
import os
import subprocess
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    path = str(tool_input.get("file_path", ""))
    if not path or not os.path.isfile(path):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    try:
        if path.endswith(".py"):
            subprocess.run(
                ["uv", "run", "--project", "apps/daemon", "ruff", "format", "--quiet", path],
                cwd=project_dir,
                capture_output=True,
                timeout=30,
                check=False,
            )
        elif path.endswith((".ts", ".tsx", ".js", ".jsx", ".css", ".json")):
            subprocess.run(
                ["pnpm", "exec", "prettier", "--write", "--log-level", "silent", path],
                cwd=os.path.join(project_dir, "apps", "desktop"),
                capture_output=True,
                timeout=30,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
