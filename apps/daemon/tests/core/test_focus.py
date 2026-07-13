"""Focus policy + restoration (Phase 5.3 slice 5).

Predictable focus management: each focus-changing action declares a
policy; the manager records the prior focus, performs the action, restores
where the policy requires it, and INDEPENDENTLY verifies the final
frontmost application.
"""

from datetime import UTC, datetime

import pytest

from thoth_daemon.core.focus import (
    FocusManager,
    FocusPolicy,
)
from thoth_daemon.macos.app_control import AppInfo, MockAppControl

T0 = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
FINDER = AppInfo(name="Finder", bundle_id="com.apple.finder", active=True)
TEXTEDIT = AppInfo(name="TextEdit", bundle_id="com.apple.TextEdit", active=True)


def _ctrl() -> MockAppControl:
    return MockAppControl(running=[FINDER])


class TestFocusChange:
    def test_keep_new_focus_keeps_the_target(self) -> None:
        ctrl = _ctrl()
        manager = FocusManager(ctrl)

        def action() -> None:
            ctrl.set_frontmost(TEXTEDIT)  # the op activates TextEdit

        _, result = manager.change_focus("TextEdit", FocusPolicy.KEEP_NEW_FOCUS, action, now=T0)
        assert ctrl.frontmost() == TEXTEDIT
        assert result.final_bundle_id == "com.apple.TextEdit"
        assert result.restored is False
        assert result.verified is True

    def test_keep_new_focus_fails_verification_when_target_did_not_focus(self) -> None:
        ctrl = _ctrl()
        manager = FocusManager(ctrl)

        _, result = manager.change_focus(
            "TextEdit", FocusPolicy.KEEP_NEW_FOCUS, lambda: None, now=T0
        )

        assert result.verified is False
        assert result.final_bundle_id == "com.apple.finder"

    def test_restore_previous_focus_returns_to_prior_app(self) -> None:
        ctrl = _ctrl()
        manager = FocusManager(ctrl)

        def action() -> None:
            ctrl.set_frontmost(TEXTEDIT)  # temporarily inspect TextEdit

        _, result = manager.change_focus(
            "TextEdit", FocusPolicy.RESTORE_PREVIOUS_FOCUS, action, now=T0
        )
        assert result.restored is True
        assert result.verified is True  # independently confirmed via frontmost()
        assert ctrl.frontmost() == FINDER  # back to the prior app

    def test_do_not_steal_focus_verifies_focus_did_not_move(self) -> None:
        ctrl = _ctrl()
        manager = FocusManager(ctrl)

        def action() -> None:
            # A well-behaved background op does NOT change focus.
            ctrl.launch("some-server")

        _, result = manager.change_focus(
            "some-server", FocusPolicy.DO_NOT_STEAL_FOCUS, action, now=T0
        )
        assert result.verified is True
        assert ctrl.frontmost() == FINDER

    def test_do_not_steal_focus_flags_a_focus_theft(self) -> None:
        ctrl = _ctrl()
        manager = FocusManager(ctrl)

        def action() -> None:
            ctrl.set_frontmost(TEXTEDIT)  # BUG: a "background" op stole focus

        _, result = manager.change_focus("TextEdit", FocusPolicy.DO_NOT_STEAL_FOCUS, action, now=T0)
        assert result.verified is False  # detected

    def test_restore_attempt_is_not_reported_as_restored_when_target_disappears(self) -> None:
        class _FailedRestoreControl(MockAppControl):
            def activate(self, name: str) -> bool:
                return False

        ctrl = _FailedRestoreControl(running=[FINDER])
        manager = FocusManager(ctrl)

        _, result = manager.change_focus(
            "TextEdit",
            FocusPolicy.RESTORE_PREVIOUS_FOCUS,
            lambda: ctrl.set_frontmost(TEXTEDIT),
            now=T0,
        )

        assert result.restored is False
        assert result.verified is False

    def test_ask_if_ambiguous_does_not_steal_and_requests_user(self) -> None:
        ctrl = _ctrl()
        manager = FocusManager(ctrl)
        called = {"n": 0}

        def action() -> None:
            called["n"] += 1
            ctrl.set_frontmost(TEXTEDIT)

        _, result = manager.change_focus("TextEdit", FocusPolicy.ASK_IF_AMBIGUOUS, action, now=T0)
        assert result.requires_user is True
        assert called["n"] == 0  # the action was NOT performed
        assert ctrl.frontmost() == FINDER

    def test_cancellation_during_transition_skips_restore(self) -> None:
        ctrl = _ctrl()
        manager = FocusManager(ctrl)

        def action() -> None:
            ctrl.set_frontmost(TEXTEDIT)

        _, result = manager.change_focus(
            "TextEdit",
            FocusPolicy.RESTORE_PREVIOUS_FOCUS,
            action,
            now=T0,
            cancelled=lambda: True,
        )
        assert result.cancelled is True
        assert result.restored is False


class TestToolFocusPolicyDeclaration:
    def test_default_tool_policy_does_not_steal_focus(self) -> None:
        from thoth_daemon.tools.app_tools import AppList

        assert AppList(MockAppControl()).focus_policy is FocusPolicy.DO_NOT_STEAL_FOCUS

    def test_app_launch_and_focus_keep_new_focus(self) -> None:
        from thoth_daemon.tools.app_tools import AppFocus, AppLaunch

        ctrl = MockAppControl()
        assert AppLaunch(ctrl).focus_policy is FocusPolicy.KEEP_NEW_FOCUS
        assert AppFocus(ctrl).focus_policy is FocusPolicy.KEEP_NEW_FOCUS

    def test_shell_and_background_service_policy_do_not_steal_focus(self) -> None:
        from thoth_daemon.tools.shell_tool import ShellRun

        assert ShellRun().focus_policy is FocusPolicy.DO_NOT_STEAL_FOCUS

    def test_browser_policies_are_per_operation(self) -> None:
        from thoth_daemon.browser.browser_adapter import MockBrowser
        from thoth_daemon.browser.session import MockBrowserSession
        from thoth_daemon.tools.browser_interaction_tools import BrowserFind, BrowserOpen
        from thoth_daemon.tools.browser_tools import BrowserRead

        assert BrowserRead(MockBrowser()).focus_policy is FocusPolicy.DO_NOT_STEAL_FOCUS
        assert BrowserFind(MockBrowserSession({})).focus_policy is FocusPolicy.DO_NOT_STEAL_FOCUS
        assert BrowserOpen(MockBrowserSession({})).focus_policy is FocusPolicy.KEEP_NEW_FOCUS

    def test_focus_policy_serializes_across_plan_boundary(self) -> None:
        from thoth_daemon.schemas import PlanStep, RiskLevel

        step = PlanStep(
            index=0,
            title="open",
            tool_name="app_launch",
            declared_risk=RiskLevel.R1,
            focus_policy=FocusPolicy.KEEP_NEW_FOCUS,
        )

        assert step.model_dump(mode="json")["focus_policy"] == "keep_new_focus"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
