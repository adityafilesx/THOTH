"""Short-lived operational dialogue state; never approval or memory."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thoth_daemon.core.dialogue import (
    ApprovalFollowUpRejected,
    ArtifactReference,
    DialogueAmbiguous,
    DialogueConstraint,
    DialogueExpired,
    DialogueIntent,
    DialogueScopeViolation,
    DialogueState,
    OperationalDialogueStore,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _artifact(path: Path, artifact_id: str = "a1", task_id: str = "t1") -> ArtifactReference:
    path.write_text("result", encoding="utf-8")
    return ArtifactReference(
        artifact_id=artifact_id,
        task_id=task_id,
        workspace_id="w1",
        path=str(path),
        created_at=NOW,
        authoritative=True,
    )


def _state(**updates: object) -> DialogueState:
    values: dict[str, object] = {
        "active_task_id": "t1",
        "workspace_id": "w1",
        "referenced_artifacts": [],
        "previous_verified_result_id": "result-1",
        "pending_question_id": None,
        "pending_approval_id": None,
        "constraints": [],
        "expires_at": NOW + timedelta(minutes=5),
    }
    values.update(updates)
    return DialogueState(**values)


class TestArtifactResolution:
    def test_recent_artifact_resolves_open_it(self, tmp_path: Path) -> None:
        artifact = _artifact(tmp_path / "report.md")
        store = OperationalDialogueStore()
        store.put(_state(referenced_artifacts=[artifact]))
        resolution = store.resolve_follow_up("t1", "Open it.", NOW)
        assert resolution.intent is DialogueIntent.OPEN_ARTIFACT
        assert resolution.artifact_id == "a1"

    def test_ambiguous_artifact_requires_clarification(self, tmp_path: Path) -> None:
        artifacts = [
            _artifact(tmp_path / "one.md", "a1"),
            _artifact(tmp_path / "two.md", "a2"),
        ]
        store = OperationalDialogueStore()
        store.put(_state(referenced_artifacts=artifacts))
        with pytest.raises(DialogueAmbiguous):
            store.resolve_follow_up("t1", "open it", NOW)

    def test_expired_artifact_fails_safely(self, tmp_path: Path) -> None:
        artifact = _artifact(tmp_path / "report.md")
        store = OperationalDialogueStore()
        store.put(_state(referenced_artifacts=[artifact], expires_at=NOW))
        with pytest.raises(DialogueExpired):
            store.resolve_follow_up("t1", "open it", NOW + timedelta(seconds=1))

    def test_missing_or_non_authoritative_artifact_is_not_resolved(self, tmp_path: Path) -> None:
        missing = ArtifactReference(
            artifact_id="a1",
            task_id="t1",
            workspace_id="w1",
            path=str(tmp_path / "missing.md"),
            created_at=NOW,
            authoritative=False,
        )
        store = OperationalDialogueStore()
        store.put(_state(referenced_artifacts=[missing]))
        with pytest.raises(DialogueExpired, match="no authoritative recent artifact"):
            store.resolve_follow_up("t1", "open it", NOW)


class TestWorkspaceAndConstraints:
    def test_recent_workspace_resolves(self) -> None:
        store = OperationalDialogueStore()
        store.put(_state(workspace_id="w1"))
        resolution = store.resolve_follow_up(
            "t1", "Use the other workspace.", NOW, authorized_workspace_ids={"w1", "w2"}
        )
        assert resolution.intent is DialogueIntent.USE_WORKSPACE
        assert resolution.workspace_id == "w2"

    def test_multiple_other_workspaces_are_ambiguous(self) -> None:
        store = OperationalDialogueStore()
        store.put(_state(workspace_id="w1"))
        with pytest.raises(DialogueAmbiguous):
            store.resolve_follow_up(
                "t1",
                "Use the other workspace.",
                NOW,
                authorized_workspace_ids={"w1", "w2", "w3"},
            )

    def test_scope_expansion_attempt_is_rejected(self) -> None:
        store = OperationalDialogueStore()
        store.put(_state())
        with pytest.raises(DialogueScopeViolation):
            store.select_workspace("t1", "unapproved", {"w1"}, NOW)

    def test_dont_push_constraint_persists(self) -> None:
        store = OperationalDialogueStore()
        store.put(_state())
        resolution = store.resolve_follow_up("t1", "Don't push.", NOW)
        assert DialogueConstraint.NO_PUSH in resolution.constraints
        assert DialogueConstraint.NO_PUSH in store.get("t1", NOW).constraints
        with pytest.raises(DialogueScopeViolation, match="no_push"):
            store.enforce_tool_constraints("t1", "git_push", NOW)

    def test_constraint_expires_with_dialogue(self) -> None:
        store = OperationalDialogueStore()
        store.put(
            _state(
                constraints=[DialogueConstraint.NO_PUSH],
                expires_at=NOW + timedelta(seconds=1),
            )
        )
        with pytest.raises(DialogueExpired):
            store.enforce_tool_constraints("t1", "git_push", NOW + timedelta(seconds=2))


class TestIsolationAndApproval:
    @pytest.mark.parametrize("text", ["yes", "approve it", "go ahead", "do it"])
    def test_pending_approval_cannot_be_replayed_by_follow_up(self, text: str) -> None:
        store = OperationalDialogueStore()
        store.put(_state(pending_approval_id="approval-1"))
        with pytest.raises(ApprovalFollowUpRejected):
            store.resolve_follow_up("t1", text, NOW)

    def test_cross_task_reference_isolation(self, tmp_path: Path) -> None:
        artifact = _artifact(tmp_path / "report.md", task_id="t1")
        store = OperationalDialogueStore()
        store.put(_state(referenced_artifacts=[artifact]))
        store.put(_state(active_task_id="t2", workspace_id="w2"))
        with pytest.raises(DialogueExpired):
            store.resolve_follow_up("t2", "open it", NOW)

    def test_restart_drops_dialogue_state(self) -> None:
        first = OperationalDialogueStore()
        first.put(_state())
        restarted = OperationalDialogueStore()
        with pytest.raises(DialogueExpired):
            restarted.get("t1", NOW)


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("Run the tests.", DialogueIntent.RUN_TESTS),
        ("Commit those changes.", DialogueIntent.COMMIT_CHANGES),
        ("Try again.", DialogueIntent.RETRY_VERIFIED_RESULT),
        ("Stop the frontend.", DialogueIntent.STOP_FRONTEND),
    ],
)
def test_named_operational_follow_ups(text: str, intent: DialogueIntent) -> None:
    store = OperationalDialogueStore()
    store.put(_state())
    resolution = store.resolve_follow_up("t1", text, NOW)
    assert resolution.intent is intent
    assert resolution.active_task_id == "t1"
