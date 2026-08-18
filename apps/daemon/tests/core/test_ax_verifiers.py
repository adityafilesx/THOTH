"""Independent Accessibility verifiers re-read current UI state."""

from datetime import UTC, date, datetime

from omnimac_daemon.core.application_profiles import (
    ApplicationProfile,
    ApplicationProfileRegistry,
    AXCapabilityRule,
    InterfaceKind,
    ProfileVerifier,
)
from omnimac_daemon.core.ax_controller import AXController
from omnimac_daemon.core.ax_verifiers import (
    AXApplicationFrontmostVerifier,
    AXCompositeVerifier,
    AXElementEnabledVerifier,
    AXElementExistsVerifier,
    AXElementFocusedVerifier,
    AXElementSelectedVerifier,
    AXElementValueVerifier,
    AXWindowExistsVerifier,
)
from omnimac_daemon.core.focus import FocusPolicy
from omnimac_daemon.macos.app_control import AppInfo, MockAppControl
from omnimac_daemon.macos.ax_permission import AXPermissionService
from omnimac_daemon.macos.semantic_ax import MockSemanticAXAdapter
from omnimac_daemon.schemas.ax import (
    AXApplicationSnapshot,
    AXElementSnapshot,
    AXValueKind,
    AXValueMetadata,
    AXVerificationExpectation,
    AXVerificationRequest,
    AXWindowSnapshot,
)
from omnimac_daemon.schemas.enums import RiskLevel

NOW = datetime(2026, 7, 14, 16, tzinfo=UTC)
BUNDLE = "me.adityalabs.omnimac.axtest"
CAPABILITY = "ax_set_value"


def _element(**updates: object) -> AXElementSnapshot:
    values: dict[str, object] = {
        "reference_id": "ref",
        "application_bundle_id": BUNDLE,
        "window_identifier": "main",
        "role": "AXTextField",
        "identifier": "field",
        "label": "Field",
        "value_metadata": AXValueMetadata(kind=AXValueKind.STRING, value="saved", length=5),
        "enabled": True,
        "focused": True,
        "selected": True,
        "visible": True,
        "child_count": 0,
        "captured_at": NOW,
    }
    values.update(updates)
    return AXElementSnapshot(**values)


def _application(element: AXElementSnapshot) -> AXApplicationSnapshot:
    window = AXWindowSnapshot(
        application_bundle_id=BUNDLE,
        identifier="main",
        title="Fixture",
        focused=True,
        element_count=1,
        elements=(element,),
        captured_at=NOW,
    )
    return AXApplicationSnapshot(
        bundle_id=BUNDLE,
        display_name="Fixture",
        process_identifier=123,
        windows=(window,),
        captured_at=NOW,
    )


def _controller(
    element: AXElementSnapshot | None = None,
) -> tuple[AXController, MockSemanticAXAdapter]:
    profile = ApplicationProfile(
        bundle_id=BUNDLE,
        display_name="Fixture",
        version="1.0.0",
        required_permissions=("accessibility",),
        verified_capabilities=(CAPABILITY,),
        experimental_capabilities=(),
        forbidden_operations=(),
        preferred_interface_order=(InterfaceKind.ACCESSIBILITY,),
        verifier_mapping={CAPABILITY: ProfileVerifier.ACCESSIBILITY_VALUE},
        default_focus_behaviour=FocusPolicy.DO_NOT_STEAL_FOCUS,
        last_real_verification_date=date(2026, 7, 14),
        ax_capability_rules={
            CAPABILITY: AXCapabilityRule(
                tool_name="ax.set_value",
                allowed_identifiers=("field",),
                allowed_verifier_identifiers=("field",),
                allowed_verifiers=tuple(AXVerificationExpectation),
                default_risk=RiskLevel.R1,
                focus_policy=FocusPolicy.RESTORE_PREVIOUS_FOCUS,
            )
        },
    )
    app = _application(element or _element())
    adapter = MockSemanticAXAdapter([app])
    return (
        AXController(
            adapter,
            AXPermissionService(trust_probe=lambda: True),
            ApplicationProfileRegistry([profile]),
            clock=lambda: NOW,
        ),
        adapter,
    )


def _request(
    expectation: AXVerificationExpectation,
    *,
    expected_value: object = None,
) -> AXVerificationRequest:
    values: dict[str, object] = {
        "application_bundle_id": BUNDLE,
        "target": {"application_bundle_id": BUNDLE, "identifier": "field"},
        "expectation": expectation,
        "timeout_s": 2,
    }
    if expected_value is not None:
        values["expected_value"] = expected_value
    return AXVerificationRequest(**values)


def test_element_exists_verifier_re_reads_current_snapshot() -> None:
    controller, adapter = _controller()
    verifier = AXElementExistsVerifier(controller)
    assert verifier.verify(_request(AXVerificationExpectation.EXISTS), CAPABILITY).passed

    empty = _application(_element()).model_copy(
        update={"windows": (_application(_element()).windows[0].model_copy(update={"elements": (), "element_count": 0}),)}
    )
    adapter.replace_application(empty)
    assert not verifier.verify(_request(AXVerificationExpectation.EXISTS), CAPABILITY).passed


def test_value_verifier_does_not_trust_action_response() -> None:
    controller, adapter = _controller()
    verifier = AXElementValueVerifier(controller)
    wanted = _request(AXVerificationExpectation.VALUE_EQUALS, expected_value="saved")
    assert verifier.verify(wanted, CAPABILITY).passed

    adapter.replace_application(_application(_element(value_metadata=AXValueMetadata(kind=AXValueKind.STRING, value="wrong", length=5))))
    assert not verifier.verify(wanted, CAPABILITY).passed


def test_enabled_focused_and_selected_verifiers() -> None:
    controller, _ = _controller()
    request_enabled = _request(AXVerificationExpectation.ENABLED)
    request_focused = _request(AXVerificationExpectation.FOCUSED)
    request_selected = _request(AXVerificationExpectation.SELECTED)
    assert AXElementEnabledVerifier(controller).verify(request_enabled, CAPABILITY).passed
    assert AXElementFocusedVerifier(controller).verify(request_focused, CAPABILITY).passed
    assert AXElementSelectedVerifier(controller).verify(request_selected, CAPABILITY).passed


def test_window_and_application_frontmost_verifiers() -> None:
    controller, _ = _controller()
    window_request = AXVerificationRequest(
        application_bundle_id=BUNDLE,
        window_identifier="main",
        expectation=AXVerificationExpectation.WINDOW_EXISTS,
    )
    assert AXWindowExistsVerifier(controller).verify(window_request, CAPABILITY).passed

    control = MockAppControl([AppInfo(name="Fixture", bundle_id=BUNDLE, active=True)])
    front_request = AXVerificationRequest(
        application_bundle_id=BUNDLE,
        expectation=AXVerificationExpectation.APPLICATION_FRONTMOST,
    )
    assert AXApplicationFrontmostVerifier(control).verify(front_request, CAPABILITY).passed


def test_composite_requires_every_fresh_child() -> None:
    controller, _ = _controller()
    composite = AXCompositeVerifier([AXElementExistsVerifier(controller), AXElementValueVerifier(controller)])
    requests = [
        _request(AXVerificationExpectation.EXISTS),
        _request(AXVerificationExpectation.VALUE_EQUALS, expected_value="wrong"),
    ]
    result = composite.verify_all(requests, CAPABILITY)
    assert not result.passed
    assert "value_equals" in result.detail
