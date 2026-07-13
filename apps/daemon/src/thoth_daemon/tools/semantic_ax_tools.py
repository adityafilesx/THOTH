"""Narrow semantic Accessibility tools; no coordinate or unrestricted action tool."""

from __future__ import annotations

import asyncio
from datetime import datetime
from time import monotonic
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from thoth_daemon.core.ax_controller import AXController, default_ax_controller
from thoth_daemon.core.ax_resolver import AXResolutionResult
from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from thoth_daemon.schemas.ax import (
    AXActionResult,
    AXApplicationSnapshot,
    AXElementQuery,
    AXElementSnapshot,
    AXPrimitive,
    AXValueMetadata,
    AXVerificationRequest,
    AXWindowSnapshot,
)
from thoth_daemon.tools.base import ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _AppIn(_In):
    bundle_id: str = Field(min_length=1, max_length=255)
    capability: str = Field(min_length=1, max_length=255)


class _QueryIn(_AppIn):
    query: AXElementQuery

    @model_validator(mode="after")
    def _query_bundle_matches(self) -> _QueryIn:
        if self.query.application_bundle_id != self.bundle_id:
            raise ValueError("AX query bundle must match bundle_id")
        return self


class _MutationIn(_QueryIn):
    expected_current_value: AXPrimitive | None = None
    expected_result: str = Field(min_length=1, max_length=4096)
    verifier: AXVerificationRequest
    timeout_s: float = Field(gt=0, le=30)

    @model_validator(mode="after")
    def _verifier_bundle_matches(self) -> _MutationIn:
        if self.verifier.application_bundle_id != self.bundle_id:
            raise ValueError("AX verifier bundle must match bundle_id")
        return self


class _SemanticTool(ToolDefinition[BaseModel, BaseModel]):
    def __init__(self, controller: AXController) -> None:
        super().__init__()
        self._controller = controller

    def requested_scope(self, args: _AppIn) -> ResourceScope:
        return ResourceScope(apps=[args.bundle_id])

    def focus_target(self, args: _AppIn) -> str:
        return args.bundle_id


class AXInspectApplicationOut(_Out):
    snapshot: AXApplicationSnapshot


class AXInspectApplicationIn(_AppIn):
    capability: Literal["ax_inspect_application"]


class AXInspectApplication(_SemanticTool):
    name = "ax.inspect_application"
    description = "Inspect a bounded semantic snapshot of an approved application."
    input_model = AXInspectApplicationIn
    output_model = AXInspectApplicationOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: AXInspectApplicationIn, dry_run: bool) -> AXInspectApplicationOut:
        return AXInspectApplicationOut(
            snapshot=self._controller.inspect_application(args.bundle_id, args.capability)
        )


class AXInspectWindowIn(_AppIn):
    capability: Literal["ax_inspect_window"]
    window_identifier: str = Field(min_length=1, max_length=4096)


class AXInspectWindowOut(_Out):
    snapshot: AXWindowSnapshot | None


class AXInspectWindow(_SemanticTool):
    name = "ax.inspect_window"
    description = "Inspect one bounded semantic window snapshot in an approved app."
    input_model = AXInspectWindowIn
    output_model = AXInspectWindowOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: AXInspectWindowIn, dry_run: bool) -> AXInspectWindowOut:
        return AXInspectWindowOut(
            snapshot=self._controller.inspect_window(
                args.bundle_id, args.capability, args.window_identifier
            )
        )


class AXFindElementIn(_QueryIn):
    capability: Literal["ax_find_element"]


class AXFindElement(_SemanticTool):
    name = "ax.find_element"
    description = "Resolve one approved semantic AX element; ambiguity fails closed."
    input_model = AXFindElementIn
    output_model = AXResolutionResult
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: AXFindElementIn, dry_run: bool) -> AXResolutionResult:
        return self._controller.resolve(args.bundle_id, args.capability, args.query)


class AXReadValueOut(_Out):
    element: AXElementSnapshot
    value_metadata: AXValueMetadata | None


class AXReadValueIn(_QueryIn):
    capability: Literal["ax_read_value"]


class AXReadValue(_SemanticTool):
    name = "ax.read_value"
    description = "Read non-sensitive value metadata from one approved semantic AX element."
    input_model = AXReadValueIn
    output_model = AXReadValueOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: AXReadValueIn, dry_run: bool) -> AXReadValueOut:
        result = self._controller.resolve(args.bundle_id, args.capability, args.query)
        if result.element is None:
            raise RuntimeError(result.rejection_reason or "AX element did not resolve")
        return AXReadValueOut(
            element=result.element,
            value_metadata=result.element.value_metadata,
        )


class AXSetValueIn(_MutationIn):
    capability: Literal["ax_set_value"]
    value: AXPrimitive


class AXSetValue(_SemanticTool):
    name = "ax.set_value"
    description = "Set a value on one approved semantic AX element."
    input_model = AXSetValueIn
    output_model = AXActionResult
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE
    focus_policy = FocusPolicy.RESTORE_PREVIOUS_FOCUS
    redaction_fields: ClassVar[list[str]] = ["value", "expected_current_value"]

    async def run(self, args: AXSetValueIn, dry_run: bool) -> AXActionResult:
        if dry_run:
            return self._controller.preview_action(
                args.bundle_id,
                args.capability,
                args.query,
                expected_current_value=args.expected_current_value,
            )
        return self._controller.set_value(
            args.bundle_id,
            args.capability,
            args.query,
            args.value,
            expected_current_value=args.expected_current_value,
        )


class AXPerformActionIn(_MutationIn):
    capability: Literal["ax_perform_action"]
    action_name: str = Field(pattern=r"^AX[A-Za-z]+$", max_length=255)


class AXPerformAction(_SemanticTool):
    name = "ax.perform_action"
    description = "Perform one profile-authorized reversible AX action."
    input_model = AXPerformActionIn
    output_model = AXActionResult
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE
    focus_policy = FocusPolicy.RESTORE_PREVIOUS_FOCUS

    async def run(self, args: AXPerformActionIn, dry_run: bool) -> AXActionResult:
        if dry_run:
            return self._controller.preview_action(
                args.bundle_id,
                args.capability,
                args.query,
                expected_current_value=args.expected_current_value,
            )
        return self._controller.perform_action(
            args.bundle_id,
            args.capability,
            args.query,
            args.action_name,
            expected_current_value=args.expected_current_value,
        )


class AXSelectOptionIn(_MutationIn):
    capability: Literal["ax_select_option"]
    option: str = Field(min_length=1, max_length=4096)


class AXSelectOption(_SemanticTool):
    name = "ax.select_option"
    description = "Select one declared option on an approved semantic AX element."
    input_model = AXSelectOptionIn
    output_model = AXActionResult
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE
    focus_policy = FocusPolicy.RESTORE_PREVIOUS_FOCUS
    redaction_fields: ClassVar[list[str]] = ["option", "expected_current_value"]

    async def run(self, args: AXSelectOptionIn, dry_run: bool) -> AXActionResult:
        if dry_run:
            return self._controller.preview_action(
                args.bundle_id,
                args.capability,
                args.query,
                expected_current_value=args.expected_current_value,
            )
        return self._controller.select_option(
            args.bundle_id,
            args.capability,
            args.query,
            args.option,
            expected_current_value=args.expected_current_value,
        )


class AXWaitForElementIn(_QueryIn):
    capability: Literal["ax_wait_for_element"]
    timeout_s: float = Field(default=5, gt=0, le=30)


class AXWaitForElement(_SemanticTool):
    name = "ax.wait_for_element"
    description = "Wait for one approved semantic AX element with a strict timeout."
    input_model = AXWaitForElementIn
    output_model = AXResolutionResult
    default_risk = RiskLevel.R0
    timeout_s = 35
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: AXWaitForElementIn, dry_run: bool) -> AXResolutionResult:
        deadline = monotonic() + args.timeout_s
        while True:
            result = self._controller.resolve(args.bundle_id, args.capability, args.query)
            if result.element is not None or result.ambiguous or monotonic() >= deadline:
                return result
            await asyncio.sleep(0.05)


class AXWaitForValueIn(_QueryIn):
    capability: Literal["ax_wait_for_value"]
    expected_value: AXPrimitive
    timeout_s: float = Field(default=5, gt=0, le=30)


class AXWaitForValueOut(_Out):
    matched: bool
    element: AXElementSnapshot | None
    value_metadata: AXValueMetadata | None
    observed_at: datetime


class AXWaitForValue(_SemanticTool):
    name = "ax.wait_for_value"
    description = "Wait for one non-sensitive semantic AX value with a strict timeout."
    input_model = AXWaitForValueIn
    output_model = AXWaitForValueOut
    default_risk = RiskLevel.R0
    timeout_s = 35
    verification = VerificationStrategy.NONE_READONLY
    redaction_fields: ClassVar[list[str]] = ["expected_value"]

    async def run(self, args: AXWaitForValueIn, dry_run: bool) -> AXWaitForValueOut:
        deadline = monotonic() + args.timeout_s
        last: AXElementSnapshot | None = None
        while True:
            result = self._controller.resolve(args.bundle_id, args.capability, args.query)
            last = result.element
            metadata = last.value_metadata if last is not None else None
            if (
                metadata is not None
                and not metadata.redacted
                and metadata.value == args.expected_value
            ):
                return AXWaitForValueOut(
                    matched=True,
                    element=last,
                    value_metadata=metadata,
                    observed_at=self._controller.now(),
                )
            if result.ambiguous or monotonic() >= deadline:
                return AXWaitForValueOut(
                    matched=False,
                    element=last,
                    value_metadata=metadata,
                    observed_at=self._controller.now(),
                )
            await asyncio.sleep(0.05)


class AXListSupportedActionsOut(_Out):
    element: AXElementSnapshot
    actions: tuple[str, ...]


class AXListSupportedActionsIn(_QueryIn):
    capability: Literal["ax_list_supported_actions"]


class AXListSupportedActions(_SemanticTool):
    name = "ax.list_supported_actions"
    description = "List the bounded AX actions exposed by one approved semantic element."
    input_model = AXListSupportedActionsIn
    output_model = AXListSupportedActionsOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: AXListSupportedActionsIn, dry_run: bool) -> AXListSupportedActionsOut:
        result = self._controller.resolve(args.bundle_id, args.capability, args.query)
        if result.element is None:
            raise RuntimeError(result.rejection_reason or "AX element did not resolve")
        return AXListSupportedActionsOut(
            element=result.element,
            actions=result.element.supported_actions,
        )


def register_semantic_ax_tools(
    registry: ToolRegistry, controller: AXController | None = None
) -> None:
    active_controller = controller or default_ax_controller()
    for tool in (
        AXInspectApplication(active_controller),
        AXInspectWindow(active_controller),
        AXFindElement(active_controller),
        AXReadValue(active_controller),
        AXSetValue(active_controller),
        AXPerformAction(active_controller),
        AXSelectOption(active_controller),
        AXWaitForElement(active_controller),
        AXWaitForValue(active_controller),
        AXListSupportedActions(active_controller),
    ):
        registry.register(tool)
