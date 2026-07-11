#!/usr/bin/env python3
"""PreToolUse hook: block dangerous commands and credential access.

Blocks (exit code 2 = deny, stderr shown to the model):
  - Access to .env files (except .env.example), SSH keys, cloud credentials,
    and macOS Keychain files -- via Bash, Read, Edit, or Write.
  - sudo.
  - Broad rm -rf (filesystem roots, home, ~, wildcards at root).
  - git push (any remote mutation of that kind).
  - Package publication (npm/pnpm/yarn/cargo publish, twine/uv publish).
  - Deployment commands (vercel/netlify/fly/heroku deploy, terraform apply,
    kubectl apply/delete, aws/gcloud deploy).

Everything else passes (exit 0). Fail-open only on malformed input so that a
hook bug cannot brick the session; the deny patterns themselves are strict.
"""

import json
import re
import sys

CRED_PATH_PATTERNS = [
    r"(^|/)\.env(\.[A-Za-z0-9_.-]+)?$",  # .env, .env.local -- but not .env.example
    r"(^|/)\.ssh(/|$)",
    r"(^|/)id_(rsa|ed25519|ecdsa|dsa)[^/]*$",
    r"(^|/)\.aws(/|$)",
    r"(^|/)\.config/gcloud(/|$)",
    r"(^|/)\.azure(/|$)",
    r"(^|/)\.kube/config",
    r"(^|/)\.netrc$",
    r"(^|/)\.npmrc$",
    r"(^|/)\.pypirc$",
    r"Library/Keychains",
    r"\.keychain(-db)?$",
    r"(^|/)credentials(\.json)?$",
]

BASH_DENY_PATTERNS: list[tuple[str, str]] = [
    (r"(^|[;&|`$(\s])sudo\s", "sudo is blocked (R3: privileged execution)"),
    (
        r"\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*[rR][a-zA-Z]*)\s+"
        r"(/|~|\$HOME|\.\.|/\*|~/\*|\$HOME/\*|(/[A-Za-z]+\s*$))",
        "broad rm -rf is blocked (R3: broad deletion)",
    ),
    (r"\bgit\s+push\b", "git push is blocked by project policy"),
    (r"\b(npm|pnpm|yarn)\s+publish\b", "package publication is blocked"),
    (r"\bcargo\s+publish\b", "package publication is blocked"),
    (r"\btwine\s+upload\b", "package publication is blocked"),
    (r"\buv\s+publish\b", "package publication is blocked"),
    (r"\b(vercel|netlify|fly|flyctl|heroku)\s+deploy\b", "deployment commands are blocked"),
    (r"\bterraform\s+(apply|destroy)\b", "deployment commands are blocked"),
    (r"\bkubectl\s+(apply|delete|create)\b", "deployment commands are blocked"),
    (r"\b(aws|gcloud)\s+[a-z-]*\s*deploy\b", "deployment commands are blocked"),
    (r"\bsecurity\s+(find|dump|export)[a-z-]*\b", "macOS Keychain access is blocked"),
]


def deny(message: str) -> None:
    print(f"BLOCKED by .claude/hooks/block_dangerous.py: {message}", file=sys.stderr)
    sys.exit(2)


def check_path(path: str) -> None:
    if path.endswith(".env.example"):
        return
    for pattern in CRED_PATH_PATTERNS:
        if re.search(pattern, path):
            deny(f"credential/secret location: {path!r} matches {pattern!r}")


def check_bash(command: str) -> None:
    for pattern, message in BASH_DENY_PATTERNS:
        if re.search(pattern, command):
            deny(f"{message} (matched {pattern!r})")
    # Credential paths referenced anywhere in a shell command.
    for token in re.split(r"[\s;|&<>()'\"]+", command):
        if token:
            for pattern in CRED_PATH_PATTERNS:
                if re.search(pattern, token) and not token.endswith(".env.example"):
                    deny(f"command touches credential location {token!r}")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool == "Bash":
        check_bash(str(tool_input.get("command", "")))
    elif tool in ("Read", "Edit", "Write", "NotebookEdit"):
        check_path(str(tool_input.get("file_path", "")))
    sys.exit(0)


if __name__ == "__main__":
    main()
