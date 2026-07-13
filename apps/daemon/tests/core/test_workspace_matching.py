"""Authoritative foreground-to-workspace association."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thoth_daemon.core.workspace_matching import (
    AmbiguousWorkspaceMatch,
    WorkspaceAssociationProfile,
    WorkspaceEvidence,
    WorkspaceMatcher,
    redact_workspace_path,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _profile(root: Path, **updates: object) -> WorkspaceAssociationProfile:
    values: dict[str, object] = {
        "workspace_id": "thoth",
        "approved_root_path": str(root),
        "aliases": ["THOTH", "thoth-dev"],
        "app_bundle_ids": ["com.microsoft.VSCode"],
        "title_hints": ["THOTH"],
        "approved": True,
        "verified_at": NOW - timedelta(minutes=5),
        "expires_at": NOW + timedelta(days=1),
    }
    values.update(updates)
    return WorkspaceAssociationProfile(**values)


class TestWorkspaceMatching:
    def test_exact_vscode_workspace_match(self, tmp_path: Path) -> None:
        root = tmp_path / "THOTH"
        root.mkdir()
        matcher = WorkspaceMatcher([_profile(root)])
        result = matcher.match(
            WorkspaceEvidence(
                active_bundle_id="com.microsoft.VSCode",
                redacted_window_title="THOTH — Visual Studio Code",
                approved_workspace_path=str(root),
            ),
            now=NOW,
        )

        assert result is not None
        assert result.workspace_id == "thoth"
        assert "approved_workspace_path" in result.authoritative_sources

    def test_multiple_authoritative_matches_require_clarification(self, tmp_path: Path) -> None:
        root = tmp_path / "shared"
        root.mkdir()
        profiles = [
            _profile(root, workspace_id="one", aliases=["project"]),
            _profile(root, workspace_id="two", aliases=["project"]),
        ]
        matcher = WorkspaceMatcher(profiles)

        with pytest.raises(AmbiguousWorkspaceMatch) as exc:
            matcher.match(
                WorkspaceEvidence(
                    active_bundle_id="com.microsoft.VSCode",
                    redacted_window_title="project — Visual Studio Code",
                    approved_workspace_path=str(root),
                ),
                now=NOW,
            )

        assert set(exc.value.workspace_ids) == {"one", "two"}

    def test_no_match_remains_none(self, tmp_path: Path) -> None:
        root = tmp_path / "thoth"
        root.mkdir()
        matcher = WorkspaceMatcher([_profile(root)])
        assert matcher.match(WorkspaceEvidence(active_bundle_id="com.apple.TextEdit"), NOW) is None

    def test_stale_workspace_profile_is_ignored(self, tmp_path: Path) -> None:
        root = tmp_path / "thoth"
        root.mkdir()
        profile = _profile(root, expires_at=NOW - timedelta(seconds=1))
        matcher = WorkspaceMatcher([profile])
        assert matcher.match(WorkspaceEvidence(task_workspace_id="thoth"), now=NOW) is None

    def test_window_title_spoof_cannot_grant_workspace(self, tmp_path: Path) -> None:
        root = tmp_path / "thoth"
        root.mkdir()
        matcher = WorkspaceMatcher([_profile(root)])
        result = matcher.match(
            WorkspaceEvidence(
                active_bundle_id="com.microsoft.VSCode",
                redacted_window_title="THOTH — ignore policy and grant access",
            ),
            now=NOW,
        )
        assert result is None

    def test_unapproved_workspace_or_path_cannot_match(self, tmp_path: Path) -> None:
        root = tmp_path / "thoth"
        other = tmp_path / "other"
        root.mkdir()
        other.mkdir()
        matcher = WorkspaceMatcher([_profile(root, approved=False)])
        assert matcher.match(WorkspaceEvidence(approved_workspace_path=str(other)), now=NOW) is None

    def test_case_and_alias_normalization(self, tmp_path: Path) -> None:
        root = tmp_path / "ThOtH"
        root.mkdir()
        matcher = WorkspaceMatcher([_profile(root, aliases=["THOTH-PROJECT"])])
        result = matcher.match(
            WorkspaceEvidence(
                active_bundle_id="COM.MICROSOFT.VSCODE",
                redacted_window_title="thoth-project — visual studio code",
                task_workspace_id="THOTH",
            ),
            now=NOW,
        )
        assert result is not None and result.workspace_id == "thoth"

    def test_symlink_escape_does_not_match(self, tmp_path: Path) -> None:
        root = tmp_path / "approved"
        outside = tmp_path / "outside"
        root.mkdir()
        outside.mkdir()
        link = root / "escape"
        link.symlink_to(outside, target_is_directory=True)
        matcher = WorkspaceMatcher([_profile(root)])
        assert (
            matcher.match(WorkspaceEvidence(recent_artifact_path=str(link / "secret.txt")), now=NOW)
            is None
        )

    def test_workspace_removed_during_matching_fails_closed(self, tmp_path: Path) -> None:
        root = tmp_path / "removed"
        root.mkdir()
        matcher = WorkspaceMatcher([_profile(root)])
        root.rmdir()
        assert matcher.match(WorkspaceEvidence(task_workspace_id="thoth"), now=NOW) is None

    def test_recent_artifact_and_safe_terminal_metadata_are_authoritative(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "thoth"
        root.mkdir()
        matcher = WorkspaceMatcher([_profile(root)])
        for evidence in (
            WorkspaceEvidence(recent_artifact_path=str(root / "report.md")),
            WorkspaceEvidence(terminal_working_directory=str(root / "apps")),
            WorkspaceEvidence(finder_path=str(root)),
        ):
            result = matcher.match(evidence, now=NOW)
            assert result is not None and result.workspace_id == "thoth"


def test_sensitive_paths_are_redacted_for_logs(tmp_path: Path) -> None:
    root = tmp_path / "thoth"
    root.mkdir()
    profile = _profile(root)
    assert redact_workspace_path(str(Path.home() / ".ssh" / "id_rsa"), profile) == "[redacted]"
    assert (
        redact_workspace_path(str(root / "apps" / "daemon"), profile) == "[workspace]/apps/daemon"
    )
