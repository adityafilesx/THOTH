"""LIVE foreground capture (Phase 5.3 slice 4).

Captures the REAL frontmost application via NSWorkspace and asserts a
plausible bundle id. Skips when PyObjC/AppKit is unavailable.
"""

from datetime import UTC, datetime

import pytest

from thoth_daemon.core.foreground import ForegroundContextBroker
from thoth_daemon.macos.app_control import default_app_control


def _appkit_available() -> bool:
    try:
        import AppKit  # type: ignore[import-untyped]  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _appkit_available(), reason="AppKit/PyObjC not available")


@pytest.mark.parametrize(
    ("bundle_id", "expected_name"),
    [
        ("com.apple.finder", "Finder"),
        ("com.apple.TextEdit", "TextEdit"),
        ("com.microsoft.VSCode", "Code"),
    ],
)
def test_live_supported_application_inventory(bundle_id: str, expected_name: str) -> None:
    running = default_app_control().list_running()
    if not running:
        pytest.skip("NSWorkspace running-application inventory is unavailable")
    match = next((app for app in running if app.bundle_id == bundle_id), None)
    if match is None:
        pytest.skip(f"{expected_name} is not currently running")
    assert match.name == expected_name
    assert match.bundle_id == bundle_id


def test_live_capture_detects_real_frontmost_app() -> None:
    broker = ForegroundContextBroker(default_app_control())
    ctx = broker.capture(reason="test", task_id=None, now=datetime.now(UTC))
    if ctx.active_bundle_id is None:
        pytest.skip("NSWorkspace has no visible frontmost application in this process context")
    assert "." in ctx.active_bundle_id
    assert ctx.active_app_name


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
