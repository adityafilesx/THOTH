"""Typed, fail-closed macOS Accessibility permission boundary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class AXPermissionStatus(StrEnum):
    NOT_DETERMINED = "not_determined"
    DENIED = "denied"
    GRANTED = "granted"
    REVOKED = "revoked"
    UNAVAILABLE = "unavailable"


class AXPermissionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AXPermissionStatus
    checked_at: datetime
    stale_after: datetime
    detail: str

    def is_stale(self, now: datetime) -> bool:
        return now >= self.stale_after


class AXPermissionError(RuntimeError):
    """The current operation cannot cross the AX permission boundary."""

    def __init__(self, snapshot: AXPermissionSnapshot | str) -> None:
        self.snapshot = snapshot if isinstance(snapshot, AXPermissionSnapshot) else None
        if self.snapshot is None:
            super().__init__(snapshot)
        else:
            super().__init__(
                f"Accessibility permission {self.snapshot.status.value}: {self.snapshot.detail}"
            )


class SettingsOpenNotAuthorized(RuntimeError):
    """Opening System Settings was not explicitly requested by the user."""


class AXPermissionService:
    """Observe TCC trust without attempting to modify it.

    Cached snapshots are for status presentation only. ``require_granted``
    always forces a new OS probe, so revocation between planning and execution
    fails before the AX adapter touches application state.
    """

    settings_url = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

    def __init__(
        self,
        *,
        trust_probe: Callable[[], bool] | None = None,
        settings_opener: Callable[[str], bool] | None = None,
        cache_ttl: timedelta = timedelta(seconds=2),
    ) -> None:
        if cache_ttl <= timedelta(0):
            raise ValueError("cache_ttl must be positive")
        self._trust_probe = trust_probe or _real_trust_probe
        self._settings_opener = settings_opener or _real_settings_opener
        self._cache_ttl = cache_ttl
        self._last: AXPermissionSnapshot | None = None
        self._ever_granted = False
        self._settings_attempted = False

    def check(
        self,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> AXPermissionSnapshot:
        observed_at = now or datetime.now(UTC)
        if self._last is not None and not force and not self._last.is_stale(observed_at):
            return self._last

        try:
            trusted = bool(self._trust_probe())
        except Exception as exc:  # framework boundary: convert to typed state
            snapshot = self._snapshot(
                AXPermissionStatus.UNAVAILABLE,
                observed_at,
                f"permission probe failed: {exc}",
            )
        else:
            if trusted:
                self._ever_granted = True
                snapshot = self._snapshot(
                    AXPermissionStatus.GRANTED,
                    observed_at,
                    "current macOS Accessibility trust is granted",
                )
            elif self._ever_granted:
                snapshot = self._snapshot(
                    AXPermissionStatus.REVOKED,
                    observed_at,
                    "previously granted Accessibility trust is no longer present",
                )
            elif self._settings_attempted:
                snapshot = self._snapshot(
                    AXPermissionStatus.DENIED,
                    observed_at,
                    "Accessibility trust remains absent after the requested settings visit",
                )
            else:
                snapshot = self._snapshot(
                    AXPermissionStatus.NOT_DETERMINED,
                    observed_at,
                    "Accessibility trust is absent and no settings visit was requested",
                )

        self._last = snapshot
        return snapshot

    def require_granted(self, *, now: datetime | None = None) -> AXPermissionSnapshot:
        snapshot = self.check(now=now, force=True)
        if snapshot.status is not AXPermissionStatus.GRANTED:
            raise AXPermissionError(snapshot)
        return snapshot

    def open_settings(self, *, user_requested: bool) -> bool:
        if not user_requested:
            raise SettingsOpenNotAuthorized(
                "opening Accessibility settings requires an explicit user request"
            )
        if self._settings_attempted:
            return False
        self._settings_attempted = True
        self._last = None
        try:
            return bool(self._settings_opener(self.settings_url))
        except Exception:
            return False

    def _snapshot(
        self,
        status: AXPermissionStatus,
        checked_at: datetime,
        detail: str,
    ) -> AXPermissionSnapshot:
        return AXPermissionSnapshot(
            status=status,
            checked_at=checked_at,
            stale_after=checked_at + self._cache_ttl,
            detail=detail,
        )


def _real_trust_probe() -> bool:
    from ApplicationServices import AXIsProcessTrusted  # type: ignore[import-untyped]

    return bool(AXIsProcessTrusted())


def _real_settings_opener(url: str) -> bool:
    from AppKit import NSWorkspace  # type: ignore[import-untyped]
    from Foundation import NSURL  # type: ignore[import-untyped]

    target: Any = NSURL.URLWithString_(url)
    if target is None:
        return False
    return bool(NSWorkspace.sharedWorkspace().openURL_(target))


def default_ax_permission_service() -> AXPermissionService:
    return AXPermissionService()
