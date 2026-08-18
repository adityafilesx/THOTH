"""Narrow semantic Accessibility tools; no coordinate or unrestricted action tool."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from threading import Event
from time import monotonic
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from omnimac_daemon.core.ax_controller import AXController, default_ax_controller
from omnimac_daemon.core.ax_resolver import AXResolutionResult
from omnimac_daemon.core.focus import FocusPolicy
from omnimac_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from omnimac_daemon.schemas.ax import (
    AXActionResult,
    AXApplicationSnapshot,
    AXElementQuery,
    AXElementSnapshot,
    AXPrimitive,
    AXValueMetadata,
    AXVerificationRequest,
    AXWindowSnapshot,
)
from omnimac_daemon.tools.base import IndependentToolVerification, ToolDefinition
from omnimac_daemon.tools.registry import ToolRegistry

MAX_AX_ACTION_SECONDS = 30.0
MAX_AX_WAIT_SECONDS = 30.0
MAX_AX_RESOLUTION_ATTEMPTS = 600
AX_POLL_INTERVAL_SECONDS = 0.05


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
    additional_verifiers: tuple[AXVerificationRequest, ...] = Field(default=(), max_length=8)
    timeout_s: float = Field(gt=0, le=MAX_AX_ACTION_SECONDS)

    @model_validator(mode="after")
    def _verifier_bundle_matches(self) -> _MutationIn:
        if self.verifier.application_bundle_id != self.bundle_id:
            raise ValueError("AX verifier bundle must match bundle_id")
        if any(verifier.application_bundle_id != self.bundle_id for verifier in self.additional_verifiers):
            raise ValueError("every AX verifier bundle must match bundle_id")
        if self.verifier.expectation.value == "exists" or any(verifier.expectation.value == "exists" for verifier in self.additional_verifiers):
            raise ValueError("AX mutation verification must prove a resulting state, not existence")
        return self


class _SemanticTool(ToolDefinition[BaseModel, BaseModel]):
    def __init__(self, controller: AXController) -> None:
        super().__init__()
        self._controller = controller

    def requested_scope(self, args: _AppIn) -> ResourceScope:
        return ResourceScope(apps=[args.bundle_id])

    def focus_target(self, args: _AppIn) -> str:
        return args.bundle_id

    def validate_authority(self, args: _AppIn) -> None:
        query = args.query if isinstance(args, _QueryIn) else None
        action_name = args.action_name if isinstance(args, AXPerformActionIn) else None
        verifiers = (args.verifier, *args.additional_verifiers) if isinstance(args, _MutationIn) else ()
        self._controller.authorize_intent(
            args.bundle_id,
            args.capability,
            self.name,
            query=query,
            action_name=action_name,
            verifiers=verifiers,
        )

    def validate_execution_authority(self, args: _AppIn) -> None:
        query = args.query if isinstance(args, _QueryIn) else None
        action_name = args.action_name if isinstance(args, AXPerformActionIn) else None
        verifiers = (args.verifier, *args.additional_verifiers) if isinstance(args, _MutationIn) else ()
        self._controller.validate_execution_intent(
            args.bundle_id,
            args.capability,
            self.name,
            query=query,
            action_name=action_name,
            verifiers=verifiers,
        )

    def bind_execution_context(
        self,
        args: _AppIn,
        *,
        task_id: str,
        step_id: str,
    ) -> None:
        self._controller.bind_diagnostics(
            task_id=task_id,
            step_id=step_id,
            tool_name=self.name,
            bundle_id=args.bundle_id,
            capability=args.capability,
            query=args.query if isinstance(args, _QueryIn) else None,
        )


class _MutationTool(_SemanticTool):
    async def _run_cancellable(
        self,
        operation: Callable[[Callable[[], bool]], AXActionResult],
    ) -> AXActionResult:
        cancelled = Event()
        try:
            return await asyncio.to_thread(operation, cancelled.is_set)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    def verify_independently(self, args: _MutationIn) -> IndependentToolVerification:
        requests = (args.verifier, *args.additional_verifiers)
        results = [self._controller.verify(request, args.capability) for request in requests]
        passed = all(result.passed for result in results)
        detail = "; ".join(f"{result.expectation.value}={'ok' if result.passed else 'fail'}" for result in results)
        return IndependentToolVerification(passed=passed, detail=detail)


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
            snapshot=await asyncio.to_thread(
                self._controller.inspect_application,
                args.bundle_id,
                args.capability,
            )
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
            snapshot=await asyncio.to_thread(
                self._controller.inspect_window,
                args.bundle_id,
                args.capability,
                args.window_identifier,
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
        return await asyncio.to_thread(
            self._controller.resolve,
            args.bundle_id,
            args.capability,
            args.query,
        )


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
        result = await asyncio.to_thread(
            self._controller.resolve,
            args.bundle_id,
            args.capability,
            args.query,
        )
        if result.element is None:
            raise RuntimeError(result.rejection_reason or "AX element did not resolve")
        return AXReadValueOut(
            element=result.element,
            value_metadata=result.element.value_metadata,
        )


class AXSetValueIn(_MutationIn):
    capability: Literal["ax_set_value"]
    value: AXPrimitive

    @model_validator(mode="after")
    def _value_verifier_matches_mutation(self) -> AXSetValueIn:
        if self.verifier.expectation.value != "value_equals" or self.verifier.target != self.query or self.verifier.expected_value != self.value:
            raise ValueError("ax.set_value requires a matching value_equals verifier")
        return self


class AXSetValue(_MutationTool):
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
            return await self._run_cancellable(
                lambda cancelled: self._controller.preview_action(
                    args.bundle_id,
                    args.capability,
                    args.query,
                    expected_current_value=args.expected_current_value,
                    verifier=args.verifier.expectation,
                    cancelled=cancelled,
                )
            )
        return await self._run_cancellable(
            lambda cancelled: self._controller.set_value(
                args.bundle_id,
                args.capability,
                args.query,
                args.value,
                expected_current_value=args.expected_current_value,
                verifier=args.verifier.expectation,
                cancelled=cancelled,
            )
        )


class AXPerformActionIn(_MutationIn):
    capability: Literal["ax_perform_action"]
    action_name: str = Field(pattern=r"^AX[A-Za-z]+$", max_length=255)


class AXPerformAction(_MutationTool):
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
            return await self._run_cancellable(
                lambda cancelled: self._controller.preview_action(
                    args.bundle_id,
                    args.capability,
                    args.query,
                    expected_current_value=args.expected_current_value,
                    action_name=args.action_name,
                    verifier=args.verifier.expectation,
                    cancelled=cancelled,
                )
            )
        return await self._run_cancellable(
            lambda cancelled: self._controller.perform_action(
                args.bundle_id,
                args.capability,
                args.query,
                args.action_name,
                expected_current_value=args.expected_current_value,
                verifier=args.verifier.expectation,
                cancelled=cancelled,
            )
        )


class AXSelectOptionIn(_MutationIn):
    capability: Literal["ax_select_option"]
    option: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def _option_verifier_matches_mutation(self) -> AXSelectOptionIn:
        if self.verifier.expectation.value != "value_equals" or self.verifier.target != self.query or self.verifier.expected_value != self.option:
            raise ValueError("ax.select_option requires a matching value_equals verifier")
        return self


class AXSelectOption(_MutationTool):
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
            return await self._run_cancellable(
                lambda cancelled: self._controller.preview_action(
                    args.bundle_id,
                    args.capability,
                    args.query,
                    expected_current_value=args.expected_current_value,
                    verifier=args.verifier.expectation,
                    cancelled=cancelled,
                )
            )
        return await self._run_cancellable(
            lambda cancelled: self._controller.select_option(
                args.bundle_id,
                args.capability,
                args.query,
                args.option,
                expected_current_value=args.expected_current_value,
                verifier=args.verifier.expectation,
                cancelled=cancelled,
            )
        )


class AXWaitForElementIn(_QueryIn):
    capability: Literal["ax_wait_for_element"]
    timeout_s: float = Field(default=5, gt=0, le=MAX_AX_WAIT_SECONDS)


class AXWaitForElement(_SemanticTool):
    name = "ax.wait_for_element"
    description = "Wait for one approved semantic AX element with a strict timeout."
    input_model = AXWaitForElementIn
    output_model = AXResolutionResult
    default_risk = RiskLevel.R0
    timeout_s = 35
    max_resolution_attempts = MAX_AX_RESOLUTION_ATTEMPTS
    verification = VerificationStrategy.NONE_READONLY

    async def run(self, args: AXWaitForElementIn, dry_run: bool) -> AXResolutionResult:
        deadline = monotonic() + args.timeout_s
        attempts = 0
        while True:
            attempts += 1
            result = await asyncio.to_thread(
                self._controller.resolve,
                args.bundle_id,
                args.capability,
                args.query,
            )
            if result.element is not None or result.ambiguous or monotonic() >= deadline or attempts >= self.max_resolution_attempts:
                return result
            await asyncio.sleep(AX_POLL_INTERVAL_SECONDS)


class AXWaitForValueIn(_QueryIn):
    capability: Literal["ax_wait_for_value"]
    expected_value: AXPrimitive
    timeout_s: float = Field(default=5, gt=0, le=MAX_AX_WAIT_SECONDS)


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
    max_resolution_attempts = MAX_AX_RESOLUTION_ATTEMPTS
    verification = VerificationStrategy.NONE_READONLY
    redaction_fields: ClassVar[list[str]] = ["expected_value"]

    async def run(self, args: AXWaitForValueIn, dry_run: bool) -> AXWaitForValueOut:
        deadline = monotonic() + args.timeout_s
        last: AXElementSnapshot | None = None
        attempts = 0
        while True:
            attempts += 1
            result = await asyncio.to_thread(
                self._controller.resolve,
                args.bundle_id,
                args.capability,
                args.query,
            )
            last = result.element
            metadata = last.value_metadata if last is not None else None
            if metadata is not None and not metadata.redacted and metadata.value == args.expected_value:
                return AXWaitForValueOut(
                    matched=True,
                    element=last,
                    value_metadata=metadata,
                    observed_at=self._controller.now(),
                )
            if result.ambiguous or monotonic() >= deadline or attempts >= self.max_resolution_attempts:
                return AXWaitForValueOut(
                    matched=False,
                    element=last,
                    value_metadata=metadata,
                    observed_at=self._controller.now(),
                )
            await asyncio.sleep(AX_POLL_INTERVAL_SECONDS)


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
        result = await asyncio.to_thread(
            self._controller.resolve,
            args.bundle_id,
            args.capability,
            args.query,
        )
        if result.element is None:
            raise RuntimeError(result.rejection_reason or "AX element did not resolve")
        return AXListSupportedActionsOut(
            element=result.element,
            actions=result.element.supported_actions,
        )


def register_semantic_ax_tools(registry: ToolRegistry, controller: AXController | None = None) -> None:
    active_controller = controller or default_ax_controller()
    tools = (
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
    )
    for tool in tools:
        active_controller.validate_tool_contract(
            tool.name,
            tool.default_risk,
            tool.focus_policy,
        )
        registry.register(tool)
