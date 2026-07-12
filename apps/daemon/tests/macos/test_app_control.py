import importlib.util

import pytest

from thoth_daemon.macos.app_control import AppInfo, MockAppControl

_HAS_APPKIT = importlib.util.find_spec("AppKit") is not None


def test_mock_list_and_frontmost() -> None:
    ac = MockAppControl(running=[AppInfo(name="Finder", bundle_id="com.apple.finder", active=True)])
    assert [a.name for a in ac.list_running()] == ["Finder"]
    assert ac.frontmost() is not None and ac.frontmost().name == "Finder"


def test_mock_launch_adds_to_running() -> None:
    ac = MockAppControl()
    assert ac.launch("Safari") is True
    assert "Safari" in [a.name for a in ac.list_running()]


def test_mock_launch_without_probe() -> None:
    ac = MockAppControl(add_on_launch=False)
    assert ac.launch("Safari") is True
    assert "Safari" not in [a.name for a in ac.list_running()]


def test_mock_activate_sets_frontmost() -> None:
    ac = MockAppControl(
        running=[
            AppInfo(name="Finder", bundle_id="f", active=True),
            AppInfo(name="Safari", bundle_id="s", active=False),
        ]
    )
    assert ac.activate("Safari") is True
    assert ac.frontmost().name == "Safari"
    assert ac.activate("Nope") is False


@pytest.mark.skipif(not _HAS_APPKIT, reason="AppKit/pyobjc not available (non-macOS)")
def test_real_list_running_nonintrusive() -> None:
    from thoth_daemon.macos.app_control import AppKitAppControl

    ac = AppKitAppControl()
    running = ac.list_running()
    assert len(running) > 0 and all(a.name for a in running)
    assert ac.frontmost() is not None  # some app is frontmost
