"""Strict cross-boundary contracts for semantic macOS Accessibility state."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from thoth_daemon.schemas.enums import FocusPolicy, Provenance


class _AXModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AXPermissionStatus(StrEnum):
    NOT_DETERMINED = "not_determined"
    DENIED = "denied"
    GRANTED = "granted"
    REVOKED = "revoked"
    UNAVAILABLE = "unavailable"


class AXPermissionState(_AXModel):
    status: AXPermissionStatus
    checked_at: datetime
    stale_after: datetime
    detail: str

    @model_validator(mode="after")
    def _positive_freshness(self) -> AXPermissionState:
        if self.stale_after <= self.checked_at:
            raise ValueError("stale_after must be later than checked_at")
        return self

    def is_stale(self, now: datetime) -> bool:
        return now >= self.stale_after


class AXValueKind(StrEnum):
    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    NONE = "none"
    UNSUPPORTED = "unsupported"


AXPrimitive = str | bool | int | float


class AXValueMetadata(_AXModel):
    kind: AXValueKind
    value: AXPrimitive | None = None
    redacted: bool = False
    length: int | None = Field(default=None, ge=0)
    truncated: bool = False

    @model_validator(mode="after")
    def _redacted_values_are_absent(self) -> AXValueMetadata:
        if self.redacted and self.value is not None:
            raise ValueError("redacted AX metadata cannot carry a value")
        if self.kind is AXValueKind.NONE and self.value is not None:
            raise ValueError("none AX metadata cannot carry a value")
        return self


class AXElementSnapshot(_AXModel):
    reference_id: str = Field(min_length=1, max_length=128)
    application_bundle_id: str = Field(min_length=1, max_length=255)
    window_identifier: str | None = Field(default=None, max_length=4096)
    window_title: str | None = Field(default=None, max_length=4096)
    role: str = Field(min_length=1, max_length=4096)
    subrole: str | None = Field(default=None, max_length=4096)
    identifier: str | None = Field(default=None, max_length=4096)
    label: str | None = Field(default=None, max_length=4096)
    description: str | None = Field(default=None, max_length=4096)
    value_metadata: AXValueMetadata | None = None
    enabled: bool | None = None
    focused: bool | None = None
    selected: bool | None = None
    visible: bool | None = None
    child_count: int = Field(ge=0)
    supported_actions: tuple[str, ...] = Field(default=(), max_length=32)
    parent_path: tuple[str, ...] = Field(default=(), max_length=12)
    captured_at: datetime
    truncated: bool = False
    provenance: Literal[Provenance.TOOL_RESULT_UNTRUSTED] = Provenance.TOOL_RESULT_UNTRUSTED


class AXWindowSnapshot(_AXModel):
    application_bundle_id: str = Field(min_length=1, max_length=255)
    identifier: str | None = Field(default=None, max_length=4096)
    title: str | None = Field(default=None, max_length=4096)
    focused: bool | None = None
    element_count: int = Field(default=0, ge=0, le=500)
    elements: tuple[AXElementSnapshot, ...] = Field(default=(), max_length=500)
    captured_at: datetime
    truncated: bool = False
    provenance: Literal[Provenance.TOOL_RESULT_UNTRUSTED] = Provenance.TOOL_RESULT_UNTRUSTED

    @model_validator(mode="after")
    def _element_count_matches(self) -> AXWindowSnapshot:
        if self.element_count != len(self.elements):
            raise ValueError("element_count must match elements")
        if any(
            element.application_bundle_id != self.application_bundle_id for element in self.elements
        ):
            raise ValueError("window elements must belong to the same application bundle")
        return self


class AXApplicationSnapshot(_AXModel):
    bundle_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=4096)
    process_identifier: int = Field(gt=0)
    windows: tuple[AXWindowSnapshot, ...] = Field(default=(), max_length=20)
    captured_at: datetime
    truncated: bool = False
    provenance: Literal[Provenance.TOOL_RESULT_UNTRUSTED] = Provenance.TOOL_RESULT_UNTRUSTED

    @model_validator(mode="after")
    def _window_bundles_match(self) -> AXApplicationSnapshot:
        if any(window.application_bundle_id != self.bundle_id for window in self.windows):
            raise ValueError("application windows must have the same bundle identifier")
        return self


class AXElementQuery(_AXModel):
    application_bundle_id: str = Field(min_length=1, max_length=255)
    window_identifier: str | None = Field(default=None, max_length=4096)
    role: str | None = Field(default=None, max_length=4096)
    subrole: str | None = Field(default=None, max_length=4096)
    identifier: str | None = Field(default=None, max_length=4096)
    label: str | None = Field(default=None, max_length=4096)
    semantic_alias: str | None = Field(default=None, max_length=4096)
    parent_path: tuple[str, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def _has_semantic_selector(self) -> AXElementQuery:
        has_role_label = self.role is not None and self.label is not None
        if not (self.identifier or has_role_label or self.semantic_alias or self.parent_path):
            raise ValueError("AX query requires a semantic selector")
        return self


class AXElementReference(_AXModel):
    application_bundle_id: str = Field(min_length=1, max_length=255)
    window_identifier: str | None = Field(default=None, max_length=4096)
    reference_id: str = Field(min_length=1, max_length=128)
    identifier: str | None = Field(default=None, max_length=4096)
    role: str = Field(min_length=1, max_length=4096)
    parent_path: tuple[str, ...] = Field(default=(), max_length=12)
    captured_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def _positive_freshness(self) -> AXElementReference:
        if self.expires_at <= self.captured_at:
            raise ValueError("AX reference must expire after capture")
        return self


class AXVerificationExpectation(StrEnum):
    EXISTS = "exists"
    VALUE_EQUALS = "value_equals"
    ENABLED = "enabled"
    FOCUSED = "focused"
    SELECTED = "selected"
    WINDOW_EXISTS = "window_exists"
    APPLICATION_FRONTMOST = "application_frontmost"


class AXVerificationRequest(_AXModel):
    application_bundle_id: str = Field(min_length=1, max_length=255)
    target: AXElementQuery | None = None
    window_identifier: str | None = Field(default=None, max_length=4096)
    expectation: AXVerificationExpectation
    expected_value: AXPrimitive | None = None
    timeout_s: float = Field(default=5, gt=0, le=30)

    @model_validator(mode="after")
    def _target_matches_expectation(self) -> AXVerificationRequest:
        if (
            self.target is not None
            and self.target.application_bundle_id != self.application_bundle_id
        ):
            raise ValueError("verification target bundle does not match request bundle")
        if (
            self.expectation
            in {
                AXVerificationExpectation.EXISTS,
                AXVerificationExpectation.VALUE_EQUALS,
                AXVerificationExpectation.ENABLED,
                AXVerificationExpectation.FOCUSED,
                AXVerificationExpectation.SELECTED,
            }
            and self.target is None
        ):
            raise ValueError("element verification requires a target")
        if (
            self.expectation is AXVerificationExpectation.WINDOW_EXISTS
            and not self.window_identifier
        ):
            raise ValueError("window verification requires a window identifier")
        if (
            self.expectation is AXVerificationExpectation.VALUE_EQUALS
            and self.expected_value is None
        ):
            raise ValueError("value verification requires an expected value")
        return self


class AXActionKind(StrEnum):
    SET_VALUE = "set_value"
    PERFORM_ACTION = "perform_action"
    SELECT_OPTION = "select_option"


class AXActionRequest(_AXModel):
    application_bundle_id: str = Field(min_length=1, max_length=255)
    capability: str = Field(min_length=1, max_length=255)
    target: AXElementQuery
    action: AXActionKind
    action_name: str | None = Field(default=None, max_length=255)
    value: AXPrimitive | None = None
    expected_current_value: AXPrimitive | None = None
    expected_result: str = Field(min_length=1, max_length=4096)
    verifier: AXVerificationRequest
    timeout_s: float = Field(gt=0, le=30)
    focus_policy: FocusPolicy
    requested_at: datetime

    @model_validator(mode="after")
    def _bind_authoritative_target(self) -> AXActionRequest:
        if self.target.application_bundle_id != self.application_bundle_id:
            raise ValueError("action target bundle does not match request bundle")
        if self.verifier.application_bundle_id != self.application_bundle_id:
            raise ValueError("action verifier bundle does not match request bundle")
        if self.action is AXActionKind.SET_VALUE and self.value is None:
            raise ValueError("set_value requires a value")
        if self.action is AXActionKind.PERFORM_ACTION and not self.action_name:
            raise ValueError("perform_action requires an action_name")
        return self


class AXActionResult(_AXModel):
    performed: bool
    target: AXElementReference | None = None
    observed_at: datetime
    detail: str = Field(max_length=4096)


class AXVerificationResult(_AXModel):
    passed: bool
    expectation: AXVerificationExpectation
    observed_at: datetime
    detail: str = Field(max_length=4096)
    observed_element: AXElementSnapshot | None = None
    observed_window: AXWindowSnapshot | None = None
