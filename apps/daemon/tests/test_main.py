from thoth_daemon.main import _managed_parent_pid, _monitor_parent


def test_managed_parent_pid_is_optional_and_strict() -> None:
    assert _managed_parent_pid({}) is None
    assert _managed_parent_pid({"THOTH_DESKTOP_PARENT_PID": "not-a-pid"}) is None
    assert _managed_parent_pid({"THOTH_DESKTOP_PARENT_PID": "1"}) is None
    assert _managed_parent_pid({"THOTH_DESKTOP_PARENT_PID": "42"}) == 42


def test_parent_monitor_requests_shutdown_when_parent_disappears() -> None:
    checks: list[int] = []
    shutdowns: list[bool] = []

    def process_exists(pid: int) -> bool:
        checks.append(pid)
        return len(checks) == 1

    _monitor_parent(
        42,
        process_exists=process_exists,
        terminate=lambda: shutdowns.append(True),
        poll_seconds=0,
    )

    assert checks == [42, 42]
    assert shutdowns == [True]
