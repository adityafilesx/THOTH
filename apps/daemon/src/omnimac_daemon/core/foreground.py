"""Foreground context broker (Phase 5.3 slice 4).

Privacy-limited foreground awareness. OmniMac snapshots the current
operational context ON DEMAND — never continuously, never as a
screenshot. Window titles and selected file paths are redacted at capture
time; captures are retained only for a bounded window, then purged.

The context is UNTRUSTED read-only data used to resolve references
("open it", "this project"); it can never approve an action or expand
scope.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

from omnimac_daemon.macos.app_control import AppControl

_REDACTED = "[redacted]"

# Secrets/PII that may appear in window titles.
_TITLE_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),  # email
    re.compile(r"\b(?:ghp|gho|sk|xox[bapr])[-_][A-Za-z0-9]{10,}\b"),  # tokens
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),  # long hex secrets
)

# Sensitive filename stems that must never be surfaced verbatim.
_SENSITIVE_FILE = re.compile(
    r"(^\.env$|(^|\.)env$|id_rsa|id_ed25519|\.pem$|\.key$|secret|password|credential|\.p12$)",
    re.IGNORECASE,
)


class ForegroundRedactor:
    def redact_title(self, title: str) -> str:
        out = title
        for pattern in _TITLE_PATTERNS:
            out = pattern.sub(_REDACTED, out)
        return out

    def redact_path(self, path: str) -> str:
        name = PurePosixPath(path).name
        if _SENSITIVE_FILE.search(name):
            parent = str(PurePosixPath(path).parent)
            return f"{parent}/{_REDACTED}"
        return path


class ForegroundContext(BaseModel):
    """A single foreground snapshot. Note: NO screenshot/image field —
    OmniMac never captures the screen."""

    model_config = ConfigDict(extra="forbid")

    captured_at: datetime
    reason: str
    active_bundle_id: str | None = None
    active_app_name: str | None = None
    active_window_title: str | None = None
    focused_ax_role: str | None = None
    focused_ax_identifier: str | None = None
    browser_domain: str | None = None
    selected_file_paths: list[str] = Field(default_factory=list)
    workspace_id: str | None = None
    previous_bundle_id: str | None = None
    task_id: str | None = None


TitleProvider = Callable[[str], str | None]
SelectionProvider = Callable[[], list[str]]
BrowserProvider = Callable[[], str | None]
WorkspaceMatcher = Callable[[ForegroundContext], str | None]


class ForegroundContextBroker:
    def __init__(
        self,
        app_control: AppControl,
        redactor: ForegroundRedactor | None = None,
        title_provider: TitleProvider | None = None,
        selection_provider: SelectionProvider | None = None,
        browser_provider: BrowserProvider | None = None,
        workspace_matcher: WorkspaceMatcher | None = None,
        retention_seconds: int = 120,
    ) -> None:
        self._app_control = app_control
        self._redactor = redactor or ForegroundRedactor()
        self._title = title_provider
        self._selection = selection_provider
        self._browser = browser_provider
        self._workspace = workspace_matcher
        self._retention = timedelta(seconds=retention_seconds)
        self._previous_bundle: str | None = None
        self._history: list[ForegroundContext] = []

    def capture(self, reason: str, task_id: str | None, now: datetime) -> ForegroundContext:
        front = self._app_control.frontmost()
        bundle = front.bundle_id if front else None
        name = front.name if front else None

        title = self._title(name) if (self._title and name) else None
        if title is not None:
            title = self._redactor.redact_title(title)

        selected = [self._redactor.redact_path(p) for p in self._selection()] if self._selection else []
        domain = self._browser() if self._browser else None

        ctx = ForegroundContext(
            captured_at=now,
            reason=reason,
            active_bundle_id=bundle,
            active_app_name=name,
            active_window_title=title,
            browser_domain=domain,
            selected_file_paths=selected,
            previous_bundle_id=(self._previous_bundle if self._previous_bundle != bundle else None),
            task_id=task_id,
        )
        if self._workspace:
            ctx = ctx.model_copy(update={"workspace_id": self._workspace(ctx)})

        self._previous_bundle = bundle
        self._history.append(ctx)
        self._purge(now)
        return ctx

    def history(self, now: datetime) -> list[ForegroundContext]:
        self._purge(now)
        return list(self._history)

    def _purge(self, now: datetime) -> None:
        cutoff = now - self._retention
        self._history = [c for c in self._history if c.captured_at >= cutoff]
