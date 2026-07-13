"""LIVE Code inventory plus authoritative THOTH workspace association."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thoth_daemon.core.workspace_matching import (
    WorkspaceAssociationProfile,
    WorkspaceEvidence,
    WorkspaceMatcher,
)
from thoth_daemon.macos.app_control import AppKitAppControl

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("AppKit") is None,
    reason="AppKit/PyObjC not available",
)


def test_live_running_code_matches_authoritative_thoth_workspace() -> None:
    code = next(
        (
            app
            for app in AppKitAppControl().list_running()
            if app.bundle_id == "com.microsoft.VSCode"
        ),
        None,
    )
    if code is None:
        pytest.skip("Visual Studio Code is not currently running")

    repo = Path.cwd().resolve()
    if not (repo / "apps" / "daemon").is_dir():
        pytest.skip("pytest is not running from the THOTH repository root")
    now = datetime.now(UTC)
    matcher = WorkspaceMatcher(
        [
            WorkspaceAssociationProfile(
                workspace_id="thoth",
                approved_root_path=str(repo),
                aliases=("THOTH",),
                app_bundle_ids=("com.microsoft.VSCode",),
                title_hints=("THOTH",),
                approved=True,
                verified_at=now,
            )
        ]
    )
    match = matcher.match(
        WorkspaceEvidence(
            active_bundle_id=code.bundle_id,
            approved_workspace_path=str(repo),
            task_workspace_id="thoth",
        ),
        now,
    )

    assert match is not None
    assert match.workspace_id == "thoth"
    assert "approved_workspace_path" in match.authoritative_sources
    assert "active_bundle_id" in match.hint_sources
