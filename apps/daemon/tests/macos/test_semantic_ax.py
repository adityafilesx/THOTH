"""Semantic AX adapter permission and mock behavior."""

from datetime import UTC, datetime

import pytest

from thoth_daemon.macos.ax_permission import AXPermissionError, AXPermissionService
from thoth_daemon.macos.semantic_ax import RealSemanticAXAdapter
from thoth_daemon.schemas.ax import AXElementSnapshot

NOW = datetime(2026, 7, 14, 15, tzinfo=UTC)


def _element() -> AXElementSnapshot:
    return AXElementSnapshot(
        reference_id="ref",
        application_bundle_id="me.adityalabs.thoth.axtest",
        window_identifier="main",
        role="AXButton",
        identifier="ax-save-button",
        label="Save",
        enabled=True,
        visible=True,
        child_count=0,
        supported_actions=("AXPress",),
        captured_at=NOW,
    )


@pytest.mark.parametrize("operation", ["inspect", "set", "perform", "select"])
def test_real_adapter_checks_current_permission_before_every_operation(operation: str) -> None:
    adapter = RealSemanticAXAdapter(
        AXPermissionService(trust_probe=lambda: False),
        clock=lambda: NOW,
    )
    element = _element()

    with pytest.raises(AXPermissionError):
        if operation == "inspect":
            adapter.inspect_application(element.application_bundle_id)
        elif operation == "set":
            adapter.set_value(element, "value")
        elif operation == "perform":
            adapter.perform_action(element, "AXPress")
        else:
            adapter.select_option(element, "Alpha")
