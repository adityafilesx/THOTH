"""Foreground context broker (Phase 5.3 slice 4).

Privacy-limited foreground awareness: snapshot-on-demand only (never
continuous, never screenshots). Window titles and selected file paths are
redacted at capture time; captures are retained only for a bounded window.
"""

from datetime import UTC, datetime, timedelta

import pytest

from thoth_daemon.core.foreground import (
    ForegroundContext,
    ForegroundContextBroker,
    ForegroundRedactor,
)
from thoth_daemon.macos.app_control import AppInfo, MockAppControl

T0 = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)


def _control(name: str, bundle: str) -> MockAppControl:
    ctrl = MockAppControl(running=[AppInfo(name=name, bundle_id=bundle, active=True)])
    return ctrl


class TestRedaction:
    def test_window_title_email_and_secret_redacted(self) -> None:
        r = ForegroundRedactor()
        out = r.redact_title("Inbox — alice@example.com — token ghp_abcdef1234567890abcd")
        assert "alice@example.com" not in out
        assert "ghp_abcdef1234567890abcd" not in out
        assert "[redacted]" in out.lower()

    def test_sensitive_filename_redacted(self) -> None:
        r = ForegroundRedactor()
        for path in ("/Users/x/.ssh/id_rsa", "/Users/x/proj/.env", "/Users/x/secrets.txt"):
            assert "[redacted]" in r.redact_path(path).lower()

    def test_ordinary_path_preserved(self) -> None:
        r = ForegroundRedactor()
        assert r.redact_path("/Users/x/proj/README.md") == "/Users/x/proj/README.md"


class TestCapture:
    def test_captures_active_app_and_bundle(self) -> None:
        broker = ForegroundContextBroker(_control("Finder", "com.apple.finder"))
        ctx = broker.capture(reason="invoked", task_id=None, now=T0)
        assert ctx.active_app_name == "Finder"
        assert ctx.active_bundle_id == "com.apple.finder"
        assert ctx.captured_at == T0

    def test_never_carries_a_screenshot_field(self) -> None:
        # Privacy invariant: the model has no image/screenshot field at all.
        assert "screenshot" not in ForegroundContext.model_fields
        assert "image" not in ForegroundContext.model_fields
        assert "ax_tree" not in ForegroundContext.model_fields
        assert "accessibility_tree" not in ForegroundContext.model_fields

    def test_title_is_redacted_at_capture(self) -> None:
        broker = ForegroundContextBroker(
            _control("Mail", "com.apple.mail"),
            title_provider=lambda app: "Re: invoice bob@corp.com",
        )
        ctx = broker.capture(reason="invoked", task_id=None, now=T0)
        assert "bob@corp.com" not in (ctx.active_window_title or "")

    def test_selected_paths_are_redacted(self) -> None:
        broker = ForegroundContextBroker(
            _control("Finder", "com.apple.finder"),
            selection_provider=lambda: ["/Users/x/.ssh/id_rsa", "/Users/x/notes.md"],
        )
        ctx = broker.capture(reason="invoked", task_id=None, now=T0)
        assert any("notes.md" in p for p in ctx.selected_file_paths)
        assert all("id_rsa" not in p for p in ctx.selected_file_paths)

    def test_previous_bundle_tracked_across_captures(self) -> None:
        ctrl = _control("Finder", "com.apple.finder")
        broker = ForegroundContextBroker(ctrl)
        broker.capture(reason="invoked", task_id=None, now=T0)
        ctrl.set_frontmost(AppInfo(name="TextEdit", bundle_id="com.apple.TextEdit", active=True))
        ctx2 = broker.capture(reason="invoked", task_id=None, now=T0 + timedelta(seconds=5))
        assert ctx2.active_bundle_id == "com.apple.TextEdit"
        assert ctx2.previous_bundle_id == "com.apple.finder"

    def test_workspace_match_uses_injected_matcher(self) -> None:
        broker = ForegroundContextBroker(
            _control("Code", "com.microsoft.VSCode"),
            workspace_matcher=lambda ctx: "thoth" if ctx.active_app_name == "Code" else None,
        )
        ctx = broker.capture(reason="invoked", task_id="t1", now=T0)
        assert ctx.workspace_id == "thoth"
        assert ctx.task_id == "t1"


class TestRetention:
    def test_history_purges_beyond_retention(self) -> None:
        broker = ForegroundContextBroker(
            _control("Finder", "com.apple.finder"), retention_seconds=60
        )
        broker.capture(reason="invoked", task_id=None, now=T0)
        broker.capture(reason="invoked", task_id=None, now=T0 + timedelta(seconds=30))
        # 5 minutes later, the first two captures are beyond retention.
        recent = broker.history(now=T0 + timedelta(minutes=5))
        assert recent == []

    def test_history_keeps_recent(self) -> None:
        broker = ForegroundContextBroker(
            _control("Finder", "com.apple.finder"), retention_seconds=300
        )
        broker.capture(reason="invoked", task_id=None, now=T0)
        recent = broker.history(now=T0 + timedelta(seconds=30))
        assert len(recent) == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
