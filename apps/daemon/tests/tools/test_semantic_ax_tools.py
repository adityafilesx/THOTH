"""Typed semantic AX tools over the full safety contract."""

import asyncio
from datetime import UTC, date, datetime
from threading import Event

import pytest
from pydantic import ValidationError

from thoth_daemon.core.application_profiles import (
    ApplicationProfile,
    ApplicationProfileRegistry,
    AXCapabilityRule,
    CapabilityForbidden,
    CapabilityTargetForbidden,
    InterfaceKind,
    ProfileVerifier,
)
from thoth_daemon.core.ax_controller import AXController
from thoth_daemon.core.ax_diagnostics import AXDiagnosticsStore
from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.macos.ax_permission import AXPermissionError, AXPermissionService
from thoth_daemon.macos.semantic_ax import MockSemanticAXAdapter
from thoth_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation
from thoth_daemon.schemas.ax import (
    AXApplicationSnapshot,
    AXElementSnapshot,
    AXValueKind,
    AXValueMetadata,
    AXVerificationExpectation,
    AXWindowSnapshot,
)
from thoth_daemon.tools.registry import ToolRegistry
from thoth_daemon.tools.semantic_ax_tools import register_semantic_ax_tools

NOW = datetime(2026, 7, 14, 15, tzinfo=UTC)
BUNDLE = "me.adityalabs.thoth.axtest"
CAPABILITIES = (
    "ax_inspect_application",
    "ax_inspect_window",
    "ax_find_element",
    "ax_read_value",
    "ax_set_value",
    "ax_perform_action",
    "ax_select_option",
    "ax_wait_for_element",
    "ax_wait_for_value",
    "ax_list_supported_actions",
)
TOOL_NAMES = tuple(name.replace("_", ".", 1) for name in CAPABILITIES)
ALL_VERIFIERS = tuple(AXVerificationExpectation)


def _rules() -> dict[str, AXCapabilityRule]:
    read_ids = ("ax-single-line-input", "ax-save-button", "ax-picker")
    rules = {
        capability: AXCapabilityRule(
            tool_name=capability.replace("_", ".", 1),
            allowed_identifiers=read_ids,
            allowed_verifier_identifiers=read_ids,
            allowed_verifiers=ALL_VERIFIERS,
            default_risk=RiskLevel.R0,
            focus_policy=FocusPolicy.DO_NOT_STEAL_FOCUS,
        )
        for capability in CAPABILITIES
        if capability
        not in {
            "ax_inspect_application",
            "ax_inspect_window",
            "ax_set_value",
            "ax_perform_action",
            "ax_select_option",
        }
    }
    rules.update(
        {
            capability: AXCapabilityRule(
                tool_name=capability.replace("_", ".", 1),
                default_risk=RiskLevel.R0,
                focus_policy=FocusPolicy.DO_NOT_STEAL_FOCUS,
            )
            for capability in ("ax_inspect_application", "ax_inspect_window")
        }
    )
    rules["ax_set_value"] = AXCapabilityRule(
        tool_name="ax.set_value",
        allowed_identifiers=("ax-single-line-input",),
        allowed_verifier_identifiers=("ax-single-line-input",),
        allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
        default_risk=RiskLevel.R1,
        focus_policy=FocusPolicy.RESTORE_PREVIOUS_FOCUS,
    )
    rules["ax_perform_action"] = AXCapabilityRule(
        tool_name="ax.perform_action",
        allowed_identifiers=("ax-save-button",),
        allowed_roles=("AXButton",),
        allowed_verifier_identifiers=("ax-save-button",),
        allowed_actions=("AXPress",),
        allowed_verifiers=(AXVerificationExpectation.ENABLED,),
        default_risk=RiskLevel.R1,
        focus_policy=FocusPolicy.RESTORE_PREVIOUS_FOCUS,
    )
    rules["ax_select_option"] = AXCapabilityRule(
        tool_name="ax.select_option",
        allowed_identifiers=("ax-picker",),
        allowed_verifier_identifiers=("ax-picker",),
        allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
        default_risk=RiskLevel.R1,
        focus_policy=FocusPolicy.RESTORE_PREVIOUS_FOCUS,
    )
    return rules


def _profile() -> ApplicationProfileRegistry:
    return ApplicationProfileRegistry(
        [
            ApplicationProfile(
                bundle_id=BUNDLE,
                display_name="THOTH Accessibility Test App",
                version="1.0.0",
                required_permissions=("accessibility",),
                verified_capabilities=CAPABILITIES,
                experimental_capabilities=(),
                forbidden_operations=("credential_dialog", "system_security_settings"),
                preferred_interface_order=(InterfaceKind.ACCESSIBILITY,),
                verifier_mapping={
                    capability: ProfileVerifier.ACCESSIBILITY_VALUE for capability in CAPABILITIES
                },
                default_focus_behaviour=FocusPolicy.RESTORE_PREVIOUS_FOCUS,
                last_real_verification_date=date(2026, 7, 14),
                ax_capability_rules=_rules(),
            )
        ]
    )


def _element(**updates: object) -> AXElementSnapshot:
    values: dict[str, object] = {
        "reference_id": "ref-input",
        "application_bundle_id": BUNDLE,
        "window_identifier": "main",
        "window_title": "Fixture",
        "role": "AXTextField",
        "identifier": "ax-single-line-input",
        "label": "Single-line input",
        "value_metadata": AXValueMetadata(kind=AXValueKind.STRING, value="", length=0),
        "enabled": True,
        "focused": False,
        "selected": False,
        "visible": True,
        "child_count": 0,
        "supported_actions": ("AXConfirm",),
        "parent_path": ("main", "text"),
        "captured_at": NOW,
    }
    values.update(updates)
    return AXElementSnapshot(**values)


def _adapter(*elements: AXElementSnapshot) -> MockSemanticAXAdapter:
    window = AXWindowSnapshot(
        application_bundle_id=BUNDLE,
        identifier="main",
        title="Fixture",
        focused=True,
        element_count=len(elements),
        elements=elements,
        captured_at=NOW,
    )
    return MockSemanticAXAdapter.from_windows(
        bundle_id=BUNDLE,
        display_name="THOTH Accessibility Test App",
        process_identifier=123,
        windows=[window],
        captured_at=NOW,
    )


def _registry(
    adapter: MockSemanticAXAdapter | None = None,
    *,
    trusted: bool = True,
    diagnostics: AXDiagnosticsStore | None = None,
) -> tuple[ToolRegistry, MockSemanticAXAdapter]:
    active_adapter = adapter or _adapter(_element())
    controller = AXController(
        active_adapter,
        AXPermissionService(trust_probe=lambda: trusted),
        _profile(),
        clock=lambda: NOW,
        diagnostics=diagnostics,
    )
    registry = ToolRegistry()
    register_semantic_ax_tools(registry, controller)
    return registry, active_adapter


def _base_args(capability: str) -> dict[str, object]:
    return {"bundle_id": BUNDLE, "capability": capability}


def _query() -> dict[str, object]:
    return {"application_bundle_id": BUNDLE, "identifier": "ax-single-line-input"}


class TestContracts:
    def test_registers_exact_ten_dotted_tools(self) -> None:
        registry, _ = _registry()
        assert all(registry.has(name) for name in TOOL_NAMES)
        assert len([tool for tool in registry.all() if tool.name.startswith("ax.")]) == 10

    def test_read_and_mutation_risk_focus_policies(self) -> None:
        registry, _ = _registry()
        for name in TOOL_NAMES:
            tool = registry.get(name)
            if name in {"ax.set_value", "ax.perform_action", "ax.select_option"}:
                assert tool.default_risk is RiskLevel.R1
                assert tool.focus_policy is FocusPolicy.RESTORE_PREVIOUS_FOCUS
            else:
                assert tool.default_risk is RiskLevel.R0
                assert tool.focus_policy is FocusPolicy.DO_NOT_STEAL_FOCUS

    def test_scope_is_exact_bundle_and_extra_arguments_are_rejected(self) -> None:
        registry, _ = _registry()
        tool = registry.get("ax.read_value")
        args = tool.input_model.model_validate({**_base_args("ax_read_value"), "query": _query()})
        assert tool.requested_scope(args) == ResourceScope(apps=[BUNDLE])
        assert tool.focus_target(args) == BUNDLE
        with pytest.raises(ValidationError):
            tool.input_model.model_validate(
                {**_base_args("ax_read_value"), "query": _query(), "screen_x": 20}
            )

    def test_tool_cannot_claim_a_different_profile_capability(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValidationError):
            registry.get("ax.perform_action").input_model.model_validate(
                {
                    **_base_args("ax_read_value"),
                    "query": _query(),
                    "action_name": "AXConfirm",
                    "expected_result": "confirmed",
                    "verifier": {
                        "application_bundle_id": BUNDLE,
                        "target": _query(),
                        "expectation": "exists",
                    },
                    "timeout_s": 2,
                }
            )


class TestReads:
    async def test_runtime_diagnostics_bind_task_and_record_resolution(self) -> None:
        diagnostics = AXDiagnosticsStore()
        registry, _ = _registry(diagnostics=diagnostics)
        tool = registry.get("ax.read_value")
        args = tool.input_model.model_validate({**_base_args("ax_read_value"), "query": _query()})
        tool.bind_execution_context(args, task_id="task-ax", step_id="step-ax")
        await tool.run(args, False)

        snapshot = diagnostics.snapshot()
        assert snapshot.current_task_id == "task-ax"
        assert snapshot.current_tool == "ax.read_value"
        assert snapshot.semantic_target is not None
        assert snapshot.semantic_target.identifier == "ax-single-line-input"
        assert snapshot.resolution_method == "identifier"
        assert snapshot.resolution_confidence == 1.0

    async def test_inspect_find_read_and_supported_actions(self) -> None:
        registry, _ = _registry()
        inspect = registry.get("ax.inspect_application")
        inspected = await inspect.run(
            inspect.input_model.model_validate(_base_args("ax_inspect_application")), False
        )
        assert inspected.snapshot.bundle_id == BUNDLE

        find = registry.get("ax.find_element")
        found = await find.run(
            find.input_model.model_validate({**_base_args("ax_find_element"), "query": _query()}),
            False,
        )
        assert found.element is not None

        read = registry.get("ax.read_value")
        value = await read.run(
            read.input_model.model_validate({**_base_args("ax_read_value"), "query": _query()}),
            False,
        )
        assert value.value_metadata is not None and value.value_metadata.value == ""

        actions = registry.get("ax.list_supported_actions")
        listed = await actions.run(
            actions.input_model.model_validate(
                {**_base_args("ax_list_supported_actions"), "query": _query()}
            ),
            False,
        )
        assert listed.actions == ("AXConfirm",)

    async def test_permission_absence_blocks_ax_but_not_registration(self) -> None:
        registry, _ = _registry(trusted=False)
        tool = registry.get("ax.inspect_application")
        with pytest.raises(AXPermissionError):
            await tool.run(
                tool.input_model.model_validate(_base_args("ax_inspect_application")), False
            )
        assert registry.has("ax.inspect_application")

    async def test_window_and_wait_tools_return_current_bounded_state(self) -> None:
        registry, _ = _registry()
        window_tool = registry.get("ax.inspect_window")
        window = await window_tool.run(
            window_tool.input_model.model_validate(
                {**_base_args("ax_inspect_window"), "window_identifier": "main"}
            ),
            False,
        )
        assert window.snapshot is not None and window.snapshot.identifier == "main"

        wait_element = registry.get("ax.wait_for_element")
        found = await wait_element.run(
            wait_element.input_model.model_validate(
                {
                    **_base_args("ax_wait_for_element"),
                    "query": _query(),
                    "timeout_s": 0.1,
                }
            ),
            False,
        )
        assert found.element is not None

        wait_value = registry.get("ax.wait_for_value")
        matched = await wait_value.run(
            wait_value.input_model.model_validate(
                {
                    **_base_args("ax_wait_for_value"),
                    "query": _query(),
                    "expected_value": "",
                    "timeout_s": 0.1,
                }
            ),
            False,
        )
        assert matched.matched


class TestMutations:
    async def test_cancellation_during_resolution_prevents_later_mutation(self) -> None:
        entered = Event()
        release = Event()

        class BlockingAdapter(MockSemanticAXAdapter):
            def inspect_application(self, bundle_id: str) -> AXApplicationSnapshot:
                entered.set()
                release.wait(timeout=2)
                return super().inspect_application(bundle_id)

        base = _adapter(_element())
        adapter = BlockingAdapter([base.inspect_application(BUNDLE)])
        registry, _ = _registry(adapter)
        tool = registry.get("ax.set_value")
        args = tool.input_model.model_validate(
            {
                **_base_args("ax_set_value"),
                "query": _query(),
                "value": "cancelled",
                "expected_current_value": "",
                "expected_result": "field equals cancelled",
                "verifier": {
                    "application_bundle_id": BUNDLE,
                    "target": _query(),
                    "expectation": "value_equals",
                    "expected_value": "cancelled",
                },
                "timeout_s": 3,
            }
        )

        running = asyncio.create_task(tool.run(args, False))
        assert await asyncio.to_thread(entered.wait, 1)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        release.set()
        await asyncio.sleep(0.01)
        assert adapter.mutations == []

    async def test_profile_rejects_unlisted_target_action_and_verifier(self) -> None:
        registry, adapter = _registry(
            _adapter(
                _element(
                    reference_id="ref-button",
                    role="AXButton",
                    identifier="ax-save-button",
                    supported_actions=("AXPress", "AXConfirm"),
                    value_metadata=None,
                )
            )
        )
        action = registry.get("ax.perform_action")
        raw = {
            **_base_args("ax_perform_action"),
            "query": {"application_bundle_id": BUNDLE, "identifier": "ax-save-button"},
            "action_name": "AXConfirm",
            "expected_result": "confirmation applied",
            "verifier": {
                "application_bundle_id": BUNDLE,
                "target": {
                    "application_bundle_id": BUNDLE,
                    "identifier": "ax-save-button",
                },
                "expectation": "enabled",
            },
            "timeout_s": 2,
        }
        with pytest.raises(CapabilityTargetForbidden, match="action"):
            await action.run(action.input_model.model_validate(raw), False)
        assert adapter.mutations == []

        read = registry.get("ax.read_value")
        with pytest.raises(CapabilityTargetForbidden, match="identifier"):
            await read.run(
                read.input_model.model_validate(
                    {
                        **_base_args("ax_read_value"),
                        "query": {
                            "application_bundle_id": BUNDLE,
                            "identifier": "injected-target",
                        },
                    }
                ),
                False,
            )

        allowed_action = action.input_model.model_validate(
            {
                **raw,
                "action_name": "AXPress",
                "additional_verifiers": (
                    {
                        "application_bundle_id": BUNDLE,
                        "target": {
                            "application_bundle_id": BUNDLE,
                            "identifier": "ax-save-button",
                        },
                        "expectation": "focused",
                    },
                ),
            }
        )
        await action.run(allowed_action, False)
        with pytest.raises(CapabilityTargetForbidden, match="verifier"):
            action.verify_independently(allowed_action)

    async def test_set_value_dry_run_is_inert_and_real_run_is_not_self_verified(self) -> None:
        registry, adapter = _registry()
        tool = registry.get("ax.set_value")
        raw = {
            **_base_args("ax_set_value"),
            "query": _query(),
            "value": "Aditya",
            "expected_current_value": "",
            "expected_result": "field equals Aditya",
            "verifier": {
                "application_bundle_id": BUNDLE,
                "target": _query(),
                "expectation": "value_equals",
                "expected_value": "Aditya",
                "timeout_s": 2,
            },
            "timeout_s": 3,
        }
        args = tool.input_model.model_validate(raw)
        preview = await tool.run(args, True)
        assert not preview.performed
        assert adapter.mutations == []

        result = await tool.run(args, False)
        assert result.performed
        assert not hasattr(result, "verified")
        assert adapter.mutations == [("set_value", "ref-input", "Aditya")]
        assert tool.verify_independently(args).passed

    async def test_expected_current_state_mismatch_fails_before_mutation(self) -> None:
        registry, adapter = _registry()
        tool = registry.get("ax.set_value")
        args = tool.input_model.model_validate(
            {
                **_base_args("ax_set_value"),
                "query": _query(),
                "value": "new",
                "expected_current_value": "old",
                "expected_result": "field equals new",
                "verifier": {
                    "application_bundle_id": BUNDLE,
                    "target": _query(),
                    "expectation": "value_equals",
                    "expected_value": "new",
                },
                "timeout_s": 3,
            }
        )
        with pytest.raises(RuntimeError, match="expected current value"):
            await tool.run(args, False)
        assert adapter.mutations == []

    async def test_forbidden_capability_cannot_be_substituted_in_tool_input(self) -> None:
        registry, _ = _registry()
        tool = registry.get("ax.perform_action")
        with pytest.raises(ValidationError):
            tool.input_model.model_validate(
                {
                    **_base_args("credential_dialog"),
                    "query": _query(),
                    "action_name": "AXPress",
                    "expected_result": "dialog accepted",
                    "verifier": {
                        "application_bundle_id": BUNDLE,
                        "target": _query(),
                        "expectation": "exists",
                    },
                    "timeout_s": 3,
                }
            )

        with pytest.raises(CapabilityForbidden):
            _profile().authorize(BUNDLE, "credential_dialog")

    async def test_action_and_option_tools_are_narrow_and_record_exact_targets(self) -> None:
        button = _element(
            reference_id="ref-button",
            role="AXButton",
            identifier="ax-save-button",
            label="Save",
            value_metadata=None,
            supported_actions=("AXPress",),
        )
        picker = _element(
            reference_id="ref-picker",
            role="AXPopUpButton",
            identifier="ax-picker",
            label="Category",
            value_metadata=AXValueMetadata(kind=AXValueKind.STRING, value="Alpha", length=5),
            supported_actions=("AXPress",),
        )
        registry, adapter = _registry(_adapter(button, picker))

        action = registry.get("ax.perform_action")
        action_args = action.input_model.model_validate(
            {
                **_base_args("ax_perform_action"),
                "query": {"application_bundle_id": BUNDLE, "identifier": "ax-save-button"},
                "action_name": "AXPress",
                "expected_result": "save action applied",
                "verifier": {
                    "application_bundle_id": BUNDLE,
                    "target": {
                        "application_bundle_id": BUNDLE,
                        "identifier": "ax-save-button",
                    },
                    "expectation": "enabled",
                },
                "timeout_s": 2,
            }
        )
        assert (await action.run(action_args, False)).performed

        select = registry.get("ax.select_option")
        select_args = select.input_model.model_validate(
            {
                **_base_args("ax_select_option"),
                "query": {"application_bundle_id": BUNDLE, "identifier": "ax-picker"},
                "option": "Beta",
                "expected_current_value": "Alpha",
                "expected_result": "category equals Beta",
                "verifier": {
                    "application_bundle_id": BUNDLE,
                    "target": {"application_bundle_id": BUNDLE, "identifier": "ax-picker"},
                    "expectation": "value_equals",
                    "expected_value": "Beta",
                },
                "timeout_s": 2,
            }
        )
        assert (await select.run(select_args, False)).performed
        assert adapter.mutations == [
            ("perform_action", "ref-button", "AXPress"),
            ("select_option", "ref-picker", "Beta"),
        ]


class TestRegistryExecution:
    async def test_registry_scope_backstop_uses_bundle_identifier(self) -> None:
        registry, _ = _registry()
        invocation = ToolInvocation(
            task_id="task",
            step_id="step",
            tool_name="ax.read_value",
            arguments={**_base_args("ax_read_value"), "query": _query()},
            effective_risk=RiskLevel.R0,
        )
        denied = await registry.execute(invocation, ResourceScope(apps=[]))
        assert not denied.ok
        allowed = await registry.execute(invocation, ResourceScope(apps=[BUNDLE]))
        assert allowed.ok
