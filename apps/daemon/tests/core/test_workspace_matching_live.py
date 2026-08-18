"""LIVE Code inventory plus authoritative OmniMac workspace association."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

from omnimac_daemon.core.workspace_matching import (
    WorkspaceAssociationProfile,
    WorkspaceEvidence,
    WorkspaceMatcher,
)
from omnimac_daemon.macos.app_control import AppKitAppControl

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("AppKit") is None,
    reason="AppKit/PyObjC not available",
)


def test_live_running_code_matches_authoritative_omnimac_workspace() -> None:
    code = next(
        (app for app in AppKitAppControl().list_running() if app.bundle_id == "com.microsoft.VSCode"),
        None,
    )
    if code is None:
        pytest.skip("Visual Studio Code is not currently running")

    repo = Path.cwd().resolve()
    if not (repo / "apps" / "daemon").is_dir():
        pytest.skip("pytest is not running from the OmniMac repository root")
    now = datetime.now(UTC)
    matcher = WorkspaceMatcher(
        [
            WorkspaceAssociationProfile(
                workspace_id="omnimac",
                approved_root_path=str(repo),
                aliases=("OmniMac",),
                app_bundle_ids=("com.microsoft.VSCode",),
                title_hints=("OmniMac",),
                approved=True,
                verified_at=now,
            )
        ]
    )
    match = matcher.match(
        WorkspaceEvidence(
            active_bundle_id=code.bundle_id,
            approved_workspace_path=str(repo),
            task_workspace_id="omnimac",
        ),
        now,
    )

    assert match is not None
    assert match.workspace_id == "omnimac"
    assert "approved_workspace_path" in match.authoritative_sources
    assert "active_bundle_id" in match.hint_sources
