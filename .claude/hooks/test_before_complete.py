#!/usr/bin/env python3
"""Stop hook: require a test run after source changes before finishing.

If tracked source files (*.py under apps/daemon, *.ts/*.tsx under apps/desktop)
are modified relative to HEAD and no pytest/vitest invocation appears in the
recent command log, block the stop once (exit 2) with a reminder. The
`stop_hook_active` guard prevents infinite loops.
"""

import json
import os
import subprocess
import sys

RECENT = 40


def recent_commands(project_dir: str) -> list[str]:
    log_path = os.path.join(project_dir, ".claude", "hooks", "command_log.jsonl")
    try:
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()[-RECENT:]
        return [json.loads(line).get("command", "") for line in lines]
    except (OSError, json.JSONDecodeError, ValueError):
        return []


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if payload.get("stop_hook_active"):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        sys.exit(0)

    daemon_changed = any(p.startswith("apps/daemon") and p.endswith(".py") for p in diff)
    desktop_changed = any(
        p.startswith("apps/desktop") and p.endswith((".ts", ".tsx")) for p in diff
    )
    if not daemon_changed and not desktop_changed:
        sys.exit(0)

    commands = " ".join(recent_commands(project_dir))
    needs: list[str] = []
    if daemon_changed and "pytest" not in commands:
        needs.append("uv run --project apps/daemon pytest apps/daemon/tests")
    if desktop_changed and ("vitest" not in commands and "pnpm -C apps/desktop test" not in commands):
        needs.append("pnpm -C apps/desktop test -- --run")

    if needs:
        print(
            "Source files changed but relevant tests have not run. "
            "Run before finishing: " + " && ".join(needs),
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
