"""Typed Accessibility permission boundary."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from omnimac_daemon.macos.app_control import AppInfo, MockAppControl
from omnimac_daemon.macos.ax_permission import (
    AXPermissionError,
    AXPermissionService,
    AXPermissionStatus,
    SettingsOpenNotAuthorized,
)

NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)


def test_initial_absence_is_not_determined() -> None:
    service = AXPermissionService(trust_probe=lambda: False)
    assert service.check(now=NOW).status is AXPermissionStatus.NOT_DETERMINED


def test_current_trust_is_granted() -> None:
    service = AXPermissionService(trust_probe=lambda: True)
    assert service.check(now=NOW).status is AXPermissionStatus.GRANTED


def test_absence_after_explicit_settings_request_is_denied() -> None:
    opened: list[str] = []
    service = AXPermissionService(
        trust_probe=lambda: False,
        settings_opener=lambda url: opened.append(url) is None,
    )

    assert service.open_settings(user_requested=True)
    assert service.check(now=NOW, force=True).status is AXPermissionStatus.DENIED
    assert opened == [service.settings_url]


def test_grant_followed_by_absence_is_revoked() -> None:
    results = iter((True, False))
    service = AXPermissionService(trust_probe=lambda: next(results))

    assert service.check(now=NOW, force=True).status is AXPermissionStatus.GRANTED
    assert service.check(now=NOW + timedelta(seconds=1), force=True).status is AXPermissionStatus.REVOKED


def test_stale_state_is_refreshed() -> None:
    probes = 0

    def probe() -> bool:
        nonlocal probes
        probes += 1
        return probes == 1

    service = AXPermissionService(trust_probe=probe, cache_ttl=timedelta(seconds=2))
    granted = service.check(now=NOW)
    cached = service.check(now=NOW + timedelta(seconds=1))
    refreshed = service.check(now=NOW + timedelta(seconds=3))

    assert granted is cached
    assert refreshed.status is AXPermissionStatus.REVOKED
    assert probes == 2


def test_probe_failure_is_unavailable() -> None:
    def broken_probe() -> bool:
        raise RuntimeError("framework unavailable")

    snapshot = AXPermissionService(trust_probe=broken_probe).check(now=NOW)
    assert snapshot.status is AXPermissionStatus.UNAVAILABLE
    assert "framework unavailable" in snapshot.detail


def test_settings_requires_explicit_user_request_and_opens_only_once() -> None:
    calls: list[str] = []
    service = AXPermissionService(
        trust_probe=lambda: False,
        settings_opener=lambda url: calls.append(url) is None,
    )

    with pytest.raises(SettingsOpenNotAuthorized):
        service.open_settings(user_requested=False)
    assert calls == []

    assert service.open_settings(user_requested=True)
    assert service.open_settings(user_requested=True) is False
    assert calls == [service.settings_url]


@pytest.mark.parametrize(
    "status_probe",
    [lambda: False, lambda: (_ for _ in ()).throw(RuntimeError("no framework"))],
)
def test_ax_action_without_current_permission_fails_closed(
    status_probe: Callable[[], bool],
) -> None:
    service = AXPermissionService(trust_probe=status_probe)
    with pytest.raises(AXPermissionError):
        service.require_granted(now=NOW)


def test_permission_revoked_between_planning_and_execution_fails_closed() -> None:
    results = iter((True, False))
    service = AXPermissionService(trust_probe=lambda: next(results))

    assert service.check(now=NOW).status is AXPermissionStatus.GRANTED
    with pytest.raises(AXPermissionError, match="revoked"):
        service.require_granted(now=NOW + timedelta(seconds=1))


def test_non_ax_application_capability_continues_without_permission() -> None:
    service = AXPermissionService(trust_probe=lambda: False)
    control = MockAppControl([AppInfo(name="Finder", bundle_id="com.apple.finder", active=True)])

    assert service.check(now=NOW).status is AXPermissionStatus.NOT_DETERMINED
    assert control.frontmost() == AppInfo(name="Finder", bundle_id="com.apple.finder", active=True)
