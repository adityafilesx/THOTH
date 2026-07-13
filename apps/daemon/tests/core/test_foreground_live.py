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


def test_live_capture_detects_real_frontmost_app() -> None:
    broker = ForegroundContextBroker(default_app_control())
    ctx = broker.capture(reason="test", task_id=None, now=datetime.now(UTC))
    # Some app is frontmost on a real desktop session; it has a bundle id
    # shaped like reverse-DNS. (In a headless CI there may be none — then
    # bundle is None and we only assert the capture did not crash.)
    if ctx.active_bundle_id is not None:
        assert "." in ctx.active_bundle_id
        assert ctx.active_app_name


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
