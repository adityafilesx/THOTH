"""macOS app control via PyObjC NSWorkspace: launch, focus, and list running
applications. None of these need Accessibility (TCC) — AX *element* interaction
(reading/clicking UI) is a separate, TCC-gated concern and is NOT here.

AppKit is imported lazily inside each real method so this module imports cleanly
on non-macOS / without pyobjc; only the real adapter's methods touch AppKit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class AppInfo:
    name: str
    bundle_id: str | None
    active: bool


class AppControl(Protocol):
    def list_running(self) -> list[AppInfo]: ...
    def frontmost(self) -> AppInfo | None: ...
    def launch(self, name: str) -> bool: ...
    def activate(self, name: str) -> bool: ...


class AppKitAppControl:
    """Real NSWorkspace-backed control (lazy AppKit import)."""

    def _ws(self) -> Any:
        from AppKit import NSWorkspace  # type: ignore[import-untyped]

        return NSWorkspace.sharedWorkspace()

    @staticmethod
    def _info(app: Any, *, active: bool | None = None) -> AppInfo | None:
        name = app.localizedName()
        if not name:
            return None
        bundle = app.bundleIdentifier()
        return AppInfo(
            name=str(name),
            bundle_id=str(bundle) if bundle else None,
            active=bool(app.isActive()) if active is None else active,
        )

    def list_running(self) -> list[AppInfo]:
        out: list[AppInfo] = []
        for app in self._ws().runningApplications():
            info = self._info(app)
            if info is not None:
                out.append(info)
        return out

    def frontmost(self) -> AppInfo | None:
        app = self._ws().frontmostApplication()
        return self._info(app, active=True) if app is not None else None

    def launch(self, name: str) -> bool:
        return bool(self._ws().launchApplication_(name))

    def activate(self, name: str) -> bool:
        from AppKit import NSApplicationActivateIgnoringOtherApps

        for app in self._ws().runningApplications():
            if app.localizedName() and str(app.localizedName()) == name:
                return bool(app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
        return False


class MockAppControl:
    """In-memory AppControl for tests (no OS calls)."""

    def __init__(self, running: list[AppInfo] | None = None, *, add_on_launch: bool = True) -> None:
        self._running = list(running or [])
        self._frontmost = self._running[0] if self._running else None
        self._add_on_launch = add_on_launch
        self.launched: list[str] = []

    def list_running(self) -> list[AppInfo]:
        return list(self._running)

    def frontmost(self) -> AppInfo | None:
        return self._frontmost

    def set_frontmost(self, app: AppInfo) -> None:
        """Test helper: make ``app`` the frontmost (and running) application."""
        if not any(a.bundle_id == app.bundle_id for a in self._running):
            self._running.append(app)
        self._frontmost = app

    def launch(self, name: str) -> bool:
        self.launched.append(name)
        if self._add_on_launch and not any(a.name == name for a in self._running):
            self._running.append(AppInfo(name=name, bundle_id=f"com.mock.{name}", active=False))
        return True

    def activate(self, name: str) -> bool:
        for app in self._running:
            if app.name == name:
                self._frontmost = app
                return True
        return False


def default_app_control() -> AppControl:
    return AppKitAppControl()
