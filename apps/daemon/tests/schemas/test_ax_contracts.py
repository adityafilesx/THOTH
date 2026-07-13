"""Strict cross-boundary contracts for semantic Accessibility state."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from thoth_daemon.schemas import FocusPolicy, Provenance
from thoth_daemon.schemas.ax import (
    AXActionKind,
    AXActionRequest,
    AXApplicationSnapshot,
    AXElementQuery,
    AXElementReference,
    AXElementSnapshot,
    AXPermissionState,
    AXPermissionStatus,
    AXValueKind,
    AXValueMetadata,
    AXVerificationExpectation,
    AXVerificationRequest,
    AXVerificationResult,
    AXWindowSnapshot,
)

NOW = datetime(2026, 7, 14, 13, tzinfo=UTC)


def _query(**updates: object) -> AXElementQuery:
    values: dict[str, object] = {
        "application_bundle_id": "me.adityalabs.thoth.axtest",
        "identifier": "ax-save-button",
    }
    values.update(updates)
    return AXElementQuery(**values)


def _element(**updates: object) -> AXElementSnapshot:
    values: dict[str, object] = {
        "reference_id": "capture-1:element-1",
        "application_bundle_id": "me.adityalabs.thoth.axtest",
        "window_identifier": "main",
        "window_title": "THOTH AX Test App",
        "role": "AXButton",
        "identifier": "ax-save-button",
        "label": "Save",
        "value_metadata": None,
        "enabled": True,
        "focused": False,
        "selected": False,
        "visible": True,
        "child_count": 0,
        "supported_actions": ["AXPress"],
        "parent_path": ["main", "actions"],
        "captured_at": NOW,
    }
    values.update(updates)
    return AXElementSnapshot(**values)


def test_snapshots_are_strict_untrusted_observations() -> None:
    element = _element()
    window = AXWindowSnapshot(
        application_bundle_id=element.application_bundle_id,
        identifier="main",
        title="THOTH AX Test App",
        focused=True,
        element_count=1,
        elements=[element],
        captured_at=NOW,
    )
    app = AXApplicationSnapshot(
        bundle_id=element.application_bundle_id,
        display_name="THOTH AX Test App",
        process_identifier=123,
        windows=[window],
        captured_at=NOW,
    )

    assert app.provenance is Provenance.TOOL_RESULT_UNTRUSTED
    with pytest.raises(ValidationError):
        AXApplicationSnapshot.model_validate(
            {**app.model_dump(), "provenance": Provenance.SYSTEM_TRUSTED}
        )
    with pytest.raises(ValidationError):
        AXElementSnapshot.model_validate({**element.model_dump(), "screen_x": 10})


def test_secure_value_metadata_cannot_carry_a_value() -> None:
    with pytest.raises(ValidationError):
        AXValueMetadata(
            kind=AXValueKind.STRING,
            value="secret",
            redacted=True,
            length=6,
        )


def test_query_requires_semantic_identity() -> None:
    with pytest.raises(ValidationError, match="semantic selector"):
        AXElementQuery(application_bundle_id="com.apple.TextEdit")


def test_reference_must_have_positive_freshness_window() -> None:
    with pytest.raises(ValidationError):
        AXElementReference(
            application_bundle_id="com.apple.TextEdit",
            reference_id="ref",
            role="AXTextField",
            parent_path=[],
            captured_at=NOW,
            expires_at=NOW,
        )


def test_action_request_binds_target_verifier_bundle_and_focus() -> None:
    verification = AXVerificationRequest(
        application_bundle_id="me.adityalabs.thoth.axtest",
        target=_query(),
        expectation=AXVerificationExpectation.VALUE_EQUALS,
        expected_value="saved",
        timeout_s=2,
    )
    request = AXActionRequest(
        application_bundle_id="me.adityalabs.thoth.axtest",
        capability="ax_set_value",
        target=_query(),
        action=AXActionKind.SET_VALUE,
        value="saved",
        expected_result="field value equals saved",
        verifier=verification,
        timeout_s=3,
        focus_policy=FocusPolicy.DO_NOT_STEAL_FOCUS,
        requested_at=NOW,
    )
    assert request.target.application_bundle_id == request.application_bundle_id

    invalid = request.model_dump()
    invalid["target"]["application_bundle_id"] = "com.apple.TextEdit"
    with pytest.raises(ValidationError, match="bundle"):
        AXActionRequest.model_validate(invalid)


def test_verification_result_serializes_without_hidden_reasoning() -> None:
    result = AXVerificationResult(
        passed=False,
        expectation=AXVerificationExpectation.ENABLED,
        observed_at=NOW,
        detail="target is disabled",
        observed_element=_element(enabled=False),
    )
    data = result.model_dump(mode="json")
    assert data["passed"] is False
    assert "reasoning" not in data


def test_permission_state_is_strict_and_serializable() -> None:
    state = AXPermissionState(
        status=AXPermissionStatus.GRANTED,
        checked_at=NOW,
        stale_after=NOW + timedelta(seconds=2),
        detail="granted",
    )
    assert state.model_dump(mode="json")["status"] == "granted"
    assert not state.is_stale(NOW + timedelta(seconds=1))
    assert state.is_stale(NOW + timedelta(seconds=2))


def test_ax_contracts_never_expose_coordinate_fields() -> None:
    schemas = (
        AXApplicationSnapshot,
        AXWindowSnapshot,
        AXElementSnapshot,
        AXElementQuery,
        AXElementReference,
        AXActionRequest,
        AXVerificationRequest,
    )
    forbidden = {"x", "y", "screen_x", "screen_y", "coordinates", "frame"}
    for schema in schemas:
        assert forbidden.isdisjoint(schema.model_fields)
