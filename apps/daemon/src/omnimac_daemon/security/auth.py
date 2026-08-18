"""Session auth primitives.

A per-session bearer token authenticates the desktop to the daemon,
mitigating threat T6 (other local processes reaching the loopback API).
The token is IPC auth material — held in memory, written 0600 for handoff,
never persisted to SQLite, and redacted from logs/audit."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def mint_token() -> str:
    return secrets.token_urlsafe(32)


def write_token_file(path: Path, token: str) -> None:
    """Write *token* to *path* with 0600 permissions, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode())
    finally:
        os.close(fd)
    os.chmod(path, 0o600)  # tighten even if the file pre-existed


def token_matches(provided: str | None, expected: str | None) -> bool:
    """Constant-time comparison that tolerates None/empty without leaking."""
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)
