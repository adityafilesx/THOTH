"""LIVE focus restoration through NSWorkspace.

The test temporarily activates a supported application and independently
restores the original frontmost application. It skips with a precise reason
when the desktop is locked/headless or no alternate supported app is running.
"""

import importlib.util
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from thoth_daemon.core.focus import FocusManager, FocusPolicy
from thoth_daemon.macos.app_control import AppKitAppControl

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("AppKit") is None,
    reason="AppKit/PyObjC not available",
)


def test_live_temporary_focus_restores_original_application() -> None:
    control = AppKitAppControl()
    before = control.frontmost()
    if before is None:
        pytest.skip("NSWorkspace has no frontmost application")
    if before.bundle_id == "com.apple.loginwindow":
        pytest.skip("interactive macOS desktop is locked (loginwindow is frontmost)")

    candidates = [
        app
        for app in control.list_running()
        if app.bundle_id
        in {
            "com.apple.finder",
            "com.apple.TextEdit",
            "com.microsoft.VSCode",
            "com.apple.Terminal",
        }
        and app.bundle_id != before.bundle_id
    ]
    if not candidates:
        pytest.skip("no alternate supported application is running")
    target = candidates[0]

    manager = FocusManager(control)

    def activate_target() -> None:
        if not control.activate(target.name):
            pytest.fail(f"could not activate {target.name}")

    _, result = manager.change_focus(
        target.name,
        FocusPolicy.RESTORE_PREVIOUS_FOCUS,
        activate_target,
        now=datetime.now(UTC),
    )

    assert result.restored is True
    assert result.verified is True
    assert result.final_bundle_id == before.bundle_id


def test_live_background_service_does_not_steal_focus() -> None:
    control = AppKitAppControl()
    manager = FocusManager(control)
    before = control.frontmost()
    if before is None:
        pytest.skip("NSWorkspace has no frontmost application")

    process: subprocess.Popen[bytes] | None = None

    def start_service() -> None:
        nonlocal process
        process = subprocess.Popen(
            [sys.executable, "-m", "http.server", "0", "--bind", "127.0.0.1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    try:
        _, result = manager.change_focus(
            "python-http-service",
            FocusPolicy.DO_NOT_STEAL_FOCUS,
            start_service,
            now=datetime.now(UTC),
        )
        assert process is not None and process.poll() is None
        assert result.verified is True
        assert result.final_bundle_id == before.bundle_id
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
