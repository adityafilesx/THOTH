"""AX adapter (Phase 4 slice 3). All tests run against MockAXAdapter —
RealAXAdapter needs Accessibility TCC and is pending live verification."""

import pytest

from thoth_daemon.macos.ax import (
    AXElementInfo,
    AXPermissionError,
    MockAXAdapter,
    RealAXAdapter,
)


def _mock() -> MockAXAdapter:
    return MockAXAdapter(
        {
            "TestApp": [
                AXElementInfo(role="AXTextField", label="thoth-input", value="", enabled=True),
                AXElementInfo(role="AXButton", label="thoth-submit", value=None, enabled=True),
                AXElementInfo(
                    role="AXStaticText", label="thoth-status", value="idle", enabled=True
                ),
            ]
        }
    )


class TestMockAdapter:
    def test_list_elements(self) -> None:
        ax = _mock()
        elements = ax.list_elements("TestApp")
        assert [e.label for e in elements] == ["thoth-input", "thoth-submit", "thoth-status"]

    def test_find_element_by_role_and_label(self) -> None:
        ax = _mock()
        el = ax.find_element("TestApp", role="AXButton", label="thoth-submit")
        assert el is not None and el.role == "AXButton"
        assert ax.find_element("TestApp", role="AXButton", label="nope") is None

    def test_read_and_set_value_round_trip(self) -> None:
        ax = _mock()
        assert ax.read_value("TestApp", "AXTextField", "thoth-input") == ""
        assert ax.set_value("TestApp", "AXTextField", "thoth-input", "hello")
        assert ax.read_value("TestApp", "AXTextField", "thoth-input") == "hello"

    def test_set_value_unknown_element_fails(self) -> None:
        ax = _mock()
        assert not ax.set_value("TestApp", "AXTextField", "ghost", "x")

    def test_perform_action(self) -> None:
        ax = _mock()
        assert ax.perform_action("TestApp", "AXButton", "thoth-submit", "AXPress")
        assert ax.actions_performed == [("TestApp", "AXButton", "thoth-submit", "AXPress")]

    def test_perform_action_on_disabled_element_fails(self) -> None:
        ax = MockAXAdapter(
            {"A": [AXElementInfo(role="AXButton", label="b", value=None, enabled=False)]}
        )
        assert not ax.perform_action("A", "AXButton", "b", "AXPress")

    def test_wait_for_element_appears_after_priming(self) -> None:
        ax = _mock()
        late = AXElementInfo(role="AXStaticText", label="thoth-done", value="ok", enabled=True)
        ax.appear_after("TestApp", late, polls=2)
        found = ax.wait_for_element("TestApp", "AXStaticText", "thoth-done", timeout_s=1.0)
        assert found is not None and found.value == "ok"

    def test_wait_for_element_times_out(self) -> None:
        ax = _mock()
        assert ax.wait_for_element("TestApp", "AXButton", "never", timeout_s=0.05) is None

    def test_unknown_app_is_empty(self) -> None:
        ax = _mock()
        assert ax.list_elements("Ghost") == []


class TestRealAdapterPermissionGate:
    def test_untrusted_process_raises_permission_error(self) -> None:
        """Without Accessibility TCC every real operation raises
        AXPermissionError (pending live verification)."""
        ax = RealAXAdapter(trust_probe=lambda: False)
        with pytest.raises(AXPermissionError):
            ax.list_elements("Finder")
        with pytest.raises(AXPermissionError):
            ax.set_value("Finder", "AXTextField", "x", "v")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
