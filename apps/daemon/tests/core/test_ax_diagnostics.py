"""Accessibility diagnostics retain only bounded semantic metadata."""

from datetime import UTC, datetime

from omnimac_daemon.core.ax_diagnostics import AXDiagnosticsStore
from omnimac_daemon.core.ax_resolver import AXResolutionResult
from omnimac_daemon.core.focus import FocusPolicy
from omnimac_daemon.schemas.ax import AXElementQuery

NOW = datetime(2026, 7, 14, 18, tzinfo=UTC)


def test_diagnostics_omit_labels_values_and_raw_trees() -> None:
    store = AXDiagnosticsStore()
    query = AXElementQuery(
        application_bundle_id="me.adityalabs.omnimac.axtest",
        role="AXButton",
        label="private document title",
    )
    store.bind(
        task_id="task",
        step_id="step",
        tool_name="ax.perform_action",
        bundle_id=query.application_bundle_id,
        query=query,
        focus_policy=FocusPolicy.RESTORE_PREVIOUS_FOCUS,
        now=NOW,
    )
    store.record_resolution(
        AXResolutionResult(
            confidence=0.99,
            candidate_count=2,
            ambiguous=True,
            rejection_reason="multiple plausible AX elements require clarification",
            freshness_timestamp=NOW,
        ),
        now=NOW,
    )

    payload = store.snapshot().model_dump(mode="json")
    assert payload["semantic_target"] == {
        "identifier": None,
        "role": "AXButton",
        "semantic_alias": None,
    }
    assert payload["clarification_required"] is True
    assert "private document title" not in str(payload)
    assert "windows" not in payload
    assert "elements" not in payload


def test_diagnostics_retain_exactly_one_latest_snapshot() -> None:
    store = AXDiagnosticsStore()
    query = AXElementQuery(
        application_bundle_id="me.adityalabs.omnimac.axtest",
        identifier="ax-save-button",
    )
    for task_id in ("old-task", "current-task"):
        store.bind(
            task_id=task_id,
            step_id="step",
            tool_name="ax.find_element",
            bundle_id=query.application_bundle_id,
            query=query,
            focus_policy=FocusPolicy.DO_NOT_STEAL_FOCUS,
            now=NOW,
        )

    assert store.max_retained_snapshots == 1
    assert store.snapshot().current_task_id == "current-task"
    assert not hasattr(store, "history")
