"""Restricted-shell command policy (pure). The shell tool runs an allowlisted
executable via argv with NO shell interpretation; this module decides what is
allowed and extracts the paths a command touches so the ScopeEnforcer can
contain them. See docs/TOOL_CONTRACTS.md §4."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from omnimac_daemon.security.paths import expand_and_resolve


class ShellPolicyError(Exception):
    pass


EXECUTABLE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "git",
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "rg",
        "grep",
        "find",
        "echo",
        "pwd",
        "make",
        "uv",
        "python",
        "python3",
        "node",
        "npm",
        "pnpm",
        "pytest",
    }
)

# Rejected anywhere in the raw command (defense in depth; also structurally
# impossible because a shell is never used).
SHELL_METACHARACTERS: frozenset[str] = frozenset(";&|`$()<>*?{}\n\r")

CONTROLLED_PATH = "/usr/bin:/bin:/usr/local/bin"


@dataclass
class ParsedCommand:
    argv: list[str]
    path_tokens: list[str] = field(default_factory=list)


def _looks_like_path(token: str) -> bool:
    return "/" in token or token.startswith("~")


def parse_command(command: str, cwd: str) -> ParsedCommand:
    """Split *command* into argv and resolve the paths it references relative
    to *cwd*. Raise ShellPolicyError for empty input or shell metacharacters."""
    if not command.strip():
        raise ShellPolicyError("empty command")
    bad = sorted({c for c in command if c in SHELL_METACHARACTERS})
    if bad:
        raise ShellPolicyError(f"shell metacharacters not allowed: {''.join(bad)!r}")
    argv = shlex.split(command)
    if not argv:
        raise ShellPolicyError("empty command")
    tokens: list[str] = []
    for token in argv[1:]:
        if _looks_like_path(token):
            base = token if token.startswith(("~", "/")) else str(Path(cwd) / token)
            tokens.append(str(expand_and_resolve(base)))
    return ParsedCommand(argv=argv, path_tokens=tokens)


def validate_executable(argv: list[str]) -> None:
    """Raise unless argv[0] is a bare, allowlisted command name."""
    exe = argv[0]
    if "/" in exe:
        raise ShellPolicyError(f"executable must be a bare command name, not a path: {exe}")
    if exe not in EXECUTABLE_ALLOWLIST:
        raise ShellPolicyError(f"executable not allowed: {exe}")
