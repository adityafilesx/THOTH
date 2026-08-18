"""Injected probes for the independent verification framework.

Verifiers never call the OS directly — they receive a ``VerifierContext``
of callables. This keeps every verifier unit-testable offline (inject a
fake), lets the daemon wire real adapters for live runs, and makes an
un-wired capability (Accessibility without TCC, browser without Playwright)
observable as ``available=False`` instead of a silent pass.
"""

from __future__ import annotations

import socket
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerifierOutcome:
    """Result of one probe. ``available=False`` means the capability was
    not wired, so the check could not run — treated as a failure, never a
    pass, and surfaced so recovery can route to the user."""

    passed: bool
    detail: str
    available: bool = True


@dataclass(frozen=True)
class GitStateProbe:
    branch: str
    clean: bool
    head: str
    ahead: int = 0
    behind: int = 0


@dataclass(frozen=True)
class BrowserStateProbe:
    url: str
    present_selectors: frozenset[str] = field(default_factory=frozenset)


@dataclass
class VerifierContext:
    """Bundle of optional probe callables. A ``None`` probe means the
    capability is not wired in this environment."""

    read_text: Callable[[str], str] | None = None
    path_exists: Callable[[str], bool] | None = None
    http_get: Callable[[str, float], tuple[int, str]] | None = None
    tcp_listening: Callable[[str, int, float], bool] | None = None
    process_running: Callable[[str], bool] | None = None
    application_running: Callable[[str], bool] | None = None
    git_probe: Callable[[str], GitStateProbe] | None = None
    ax_value: Callable[[str, str], str | None] | None = None
    browser_probe: Callable[[], BrowserStateProbe] | None = None

    @classmethod
    def with_real_probes(cls) -> VerifierContext:
        """Wire the probes that need no special TCC permission: filesystem,
        TCP, HTTP, process table, and git. Accessibility, application, and
        browser probes stay ``None`` here — the daemon injects those from
        the AX/app/Playwright adapters when they are available (labelled
        'pending live verification' until then)."""
        return cls(
            read_text=_real_read_text,
            path_exists=_real_path_exists,
            http_get=_real_http_get,
            tcp_listening=_real_tcp_listening,
            process_running=_real_process_running,
            git_probe=_real_git_probe,
        )


def _real_read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _real_path_exists(path: str) -> bool:
    import os

    return os.path.exists(path)


def _real_http_get(url: str, timeout: float) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:  # non-2xx still carries a status
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return int(exc.code), body


def _real_tcp_listening(host: str, port: int, timeout: float) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _real_process_running(pattern: str) -> bool:
    try:
        # Fixed argv, shell=False, read-only process listing (no untrusted input).
        out = subprocess.run(
            ["ps", "-axo", "command"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return any(pattern in line for line in out.stdout.splitlines())


def _real_git_probe(repo: str) -> GitStateProbe:
    def _git(*args: str) -> str:
        # Fixed 'git' subcommands, shell=False, read-only status/rev-parse.
        out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=10, check=True)
        return out.stdout.strip()

    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    clean = status == ""
    ahead = behind = 0
    try:
        counts = _git("rev-list", "--left-right", "--count", "@{upstream}...HEAD")
        behind_s, ahead_s = counts.split()
        ahead, behind = int(ahead_s), int(behind_s)
    except (subprocess.CalledProcessError, ValueError):
        pass  # no upstream configured
    return GitStateProbe(branch=branch, clean=clean, head=head, ahead=ahead, behind=behind)
