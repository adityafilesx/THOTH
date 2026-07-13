"""Capability, permission, resolution, and mutation boundary for AX tools."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from thoth_daemon.core.application_profiles import (
    ApplicationProfileRegistry,
    build_default_application_profiles,
)
from thoth_daemon.core.ax_diagnostics import AXDiagnosticsStore
from thoth_daemon.core.ax_resolver import AXResolutionResult, AXResolver
from thoth_daemon.macos.app_control import AppControl, default_app_control
from thoth_daemon.macos.ax_permission import (
    AXPermissionError,
    AXPermissionService,
    default_ax_permission_service,
)
from thoth_daemon.macos.semantic_ax import RealSemanticAXAdapter, SemanticAXAdapter
from thoth_daemon.schemas.ax import (
    AXActionResult,
    AXApplicationSnapshot,
    AXElementQuery,
    AXElementReference,
    AXElementSnapshot,
    AXPrimitive,
    AXVerificationExpectation,
    AXVerificationRequest,
    AXVerificationResult,
    AXWindowSnapshot,
)


class AXOperationCancelled(RuntimeError):
    pass


class AXController:
    def __init__(
        self,
        adapter: SemanticAXAdapter,
        permissions: AXPermissionService,
        profiles: ApplicationProfileRegistry,
        resolver: AXResolver | None = None,
        clock: Callable[[], datetime] | None = None,
        app_control: AppControl | None = None,
        diagnostics: AXDiagnosticsStore | None = None,
    ) -> None:
        self._adapter = adapter
        self._permissions = permissions
        self._profiles = profiles
        self._resolver = resolver or AXResolver()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._app_control = app_control
        self._diagnostics = diagnostics

    def now(self) -> datetime:
        return self._clock()

    def validate_tool_contract(
        self,
        tool_name: str,
        default_risk: object,
        focus_policy: object,
    ) -> None:
        from thoth_daemon.core.focus import FocusPolicy
        from thoth_daemon.schemas import RiskLevel

        if not isinstance(default_risk, RiskLevel) or not isinstance(focus_policy, FocusPolicy):
            raise TypeError("AX tool risk and focus policy must be typed")
        self._profiles.validate_ax_tool_contract(tool_name, default_risk, focus_policy)

    def authorize_intent(
        self,
        bundle_id: str,
        capability: str,
        tool_name: str,
        *,
        query: AXElementQuery | None = None,
        action_name: str | None = None,
        verifiers: tuple[AXVerificationRequest, ...] = (),
    ) -> None:
        """Authorize model/planner arguments without touching live AX state."""
        self._authorize(
            bundle_id,
            capability,
            tool_name=tool_name,
            identifier=query.identifier if query is not None else None,
            role=query.role if query is not None else None,
            action=action_name,
            require_target=query is not None,
        )
        for verifier in verifiers:
            target = verifier.target
            self._authorize(
                bundle_id,
                capability,
                tool_name=tool_name,
                identifier=target.identifier if target is not None else None,
                role=target.role if target is not None else None,
                verifier=verifier.expectation,
                require_target=target is not None,
                verification_target=True,
            )

    def validate_execution_intent(
        self,
        bundle_id: str,
        capability: str,
        tool_name: str,
        *,
        query: AXElementQuery | None = None,
        action_name: str | None = None,
        verifiers: tuple[AXVerificationRequest, ...] = (),
    ) -> None:
        self.authorize_intent(
            bundle_id,
            capability,
            tool_name,
            query=query,
            action_name=action_name,
            verifiers=verifiers,
        )
        try:
            self._permissions.require_granted(now=self.now())
        except AXPermissionError as exc:
            if self._diagnostics is not None:
                self._diagnostics.record_permission_error(str(exc), now=self.now())
            raise

    def bind_diagnostics(
        self,
        *,
        task_id: str,
        step_id: str,
        tool_name: str,
        bundle_id: str,
        capability: str,
        query: AXElementQuery | None,
    ) -> None:
        if self._diagnostics is None:
            return
        rule = self._profiles.ax_rule(bundle_id, capability)
        self._diagnostics.bind(
            task_id=task_id,
            step_id=step_id,
            tool_name=tool_name,
            bundle_id=bundle_id,
            query=query,
            focus_policy=rule.focus_policy,
            now=self.now(),
        )

    def inspect_application(self, bundle_id: str, capability: str) -> AXApplicationSnapshot:
        self._authorize(bundle_id, capability, tool_name="ax.inspect_application")
        self._permissions.require_granted(now=self.now())
        snapshot = self._adapter.inspect_application(bundle_id)
        if snapshot.bundle_id != bundle_id:
            raise RuntimeError("AX adapter returned a cross-application snapshot")
        return snapshot

    def inspect_window(
        self,
        bundle_id: str,
        capability: str,
        window_identifier: str,
        *,
        verifier: AXVerificationExpectation | None = None,
    ) -> AXWindowSnapshot | None:
        self._authorize(
            bundle_id,
            capability,
            verifier=verifier,
            require_target=False,
        )
        self._permissions.require_granted(now=self.now())
        snapshot = self._adapter.inspect_window(bundle_id, window_identifier)
        if snapshot is not None and snapshot.application_bundle_id != bundle_id:
            raise RuntimeError("AX adapter returned a cross-application window")
        return snapshot

    def resolve(
        self,
        bundle_id: str,
        capability: str,
        query: AXElementQuery,
        *,
        require_enabled: bool = False,
        verifier: AXVerificationExpectation | None = None,
        verification_target: bool = False,
    ) -> AXResolutionResult:
        self._authorize(
            bundle_id,
            capability,
            identifier=query.identifier,
            role=query.role,
            verifier=verifier,
            verification_target=verification_target,
        )
        if query.application_bundle_id != bundle_id:
            raise RuntimeError("AX query bundle does not match the approved bundle")
        self._permissions.require_granted(now=self.now())
        snapshot = self._adapter.inspect_application(bundle_id)
        # A focused modal changes the active interaction surface. Never reach
        # through it to a background window merely because an old semantic
        # selector still matches there. Explicit modal handling requires a
        # separately profile-authorized target.
        focused_windows = tuple(window for window in snapshot.windows if window.focused is True)
        active_windows = focused_windows or snapshot.windows
        elements = [element for window in active_windows for element in window.elements]
        result = self._resolver.resolve(
            query,
            elements,
            now=self.now(),
            capability_authorized=True,
            require_enabled=require_enabled,
        )
        if result.element is not None:
            self._authorize(
                bundle_id,
                capability,
                identifier=result.element.identifier,
                role=result.element.role,
                verifier=verifier,
                resolved_target=True,
                verification_target=verification_target,
            )
        if self._diagnostics is not None:
            self._diagnostics.record_resolution(result, now=self.now())
        return result

    def preview_action(
        self,
        bundle_id: str,
        capability: str,
        query: AXElementQuery,
        *,
        expected_current_value: AXPrimitive | None = None,
        action_name: str | None = None,
        verifier: AXVerificationExpectation | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> AXActionResult:
        element = self._require_element(
            bundle_id,
            capability,
            query,
            expected_current_value=expected_current_value,
            action_name=action_name,
            verifier=verifier,
            cancelled=cancelled,
        )
        return AXActionResult(
            performed=False,
            target=self._reference(element),
            observed_at=self.now(),
            detail="dry-run preview; no AX mutation performed",
        )

    def set_value(
        self,
        bundle_id: str,
        capability: str,
        query: AXElementQuery,
        value: AXPrimitive,
        *,
        expected_current_value: AXPrimitive | None = None,
        verifier: AXVerificationExpectation,
        cancelled: Callable[[], bool] | None = None,
    ) -> AXActionResult:
        element = self._require_element(
            bundle_id,
            capability,
            query,
            expected_current_value=expected_current_value,
            verifier=verifier,
            cancelled=cancelled,
        )
        self._raise_if_cancelled(cancelled)
        self._permissions.require_granted(now=self.now())
        self._raise_if_cancelled(cancelled)
        if not self._adapter.set_value(element, value):
            raise RuntimeError("AX set_value did not complete")
        return self._action_result(
            element, "AX set_value completed; independent verification pending"
        )

    def perform_action(
        self,
        bundle_id: str,
        capability: str,
        query: AXElementQuery,
        action_name: str,
        *,
        expected_current_value: AXPrimitive | None = None,
        verifier: AXVerificationExpectation,
        cancelled: Callable[[], bool] | None = None,
    ) -> AXActionResult:
        element = self._require_element(
            bundle_id,
            capability,
            query,
            expected_current_value=expected_current_value,
            action_name=action_name,
            verifier=verifier,
            cancelled=cancelled,
        )
        self._raise_if_cancelled(cancelled)
        if action_name not in element.supported_actions:
            raise RuntimeError(
                f"AX action {action_name!r} is not supported by the resolved element"
            )
        self._permissions.require_granted(now=self.now())
        self._raise_if_cancelled(cancelled)
        if not self._adapter.perform_action(element, action_name):
            raise RuntimeError(f"AX action {action_name!r} did not complete")
        return self._action_result(element, "AX action completed; independent verification pending")

    def select_option(
        self,
        bundle_id: str,
        capability: str,
        query: AXElementQuery,
        option: str,
        *,
        expected_current_value: AXPrimitive | None = None,
        verifier: AXVerificationExpectation,
        cancelled: Callable[[], bool] | None = None,
    ) -> AXActionResult:
        element = self._require_element(
            bundle_id,
            capability,
            query,
            expected_current_value=expected_current_value,
            verifier=verifier,
            cancelled=cancelled,
        )
        self._raise_if_cancelled(cancelled)
        self._permissions.require_granted(now=self.now())
        self._raise_if_cancelled(cancelled)
        if not self._adapter.select_option(element, option):
            raise RuntimeError("AX option selection did not complete")
        return self._action_result(
            element, "AX option selection completed; independent verification pending"
        )

    def verify(
        self,
        request: AXVerificationRequest,
        capability: str,
    ) -> AXVerificationResult:
        from thoth_daemon.core.ax_verifiers import AXVerifierDispatcher

        target = request.target
        self._authorize(
            request.application_bundle_id,
            capability,
            identifier=target.identifier if target is not None else None,
            role=target.role if target is not None else None,
            verifier=request.expectation,
            require_target=target is not None,
            verification_target=True,
        )
        result = AXVerifierDispatcher(self, self._app_control).verify(request, capability)
        if self._diagnostics is not None:
            self._diagnostics.record_verification(result, now=self.now())
        return result

    def _require_element(
        self,
        bundle_id: str,
        capability: str,
        query: AXElementQuery,
        *,
        expected_current_value: AXPrimitive | None,
        action_name: str | None = None,
        verifier: AXVerificationExpectation | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> AXElementSnapshot:
        self._raise_if_cancelled(cancelled)
        result = self.resolve(
            bundle_id,
            capability,
            query,
            require_enabled=True,
            verifier=verifier,
        )
        self._raise_if_cancelled(cancelled)
        self._authorize(
            bundle_id,
            capability,
            identifier=result.element.identifier if result.element is not None else None,
            role=result.element.role if result.element is not None else None,
            action=action_name,
            verifier=verifier,
            resolved_target=result.element is not None,
        )
        if result.element is None:
            raise RuntimeError(result.rejection_reason or "AX element did not resolve")
        observed = (
            result.element.value_metadata.value
            if result.element.value_metadata is not None
            else None
        )
        if expected_current_value is not None and observed != expected_current_value:
            raise RuntimeError("expected current value did not match observed state")
        return result.element

    @staticmethod
    def _raise_if_cancelled(cancelled: Callable[[], bool] | None) -> None:
        if cancelled is not None and cancelled():
            raise AXOperationCancelled("AX operation cancelled before mutation")

    def _authorize(
        self,
        bundle_id: str,
        capability: str,
        *,
        tool_name: str | None = None,
        identifier: str | None = None,
        role: str | None = None,
        action: str | None = None,
        verifier: AXVerificationExpectation | None = None,
        resolved_target: bool = False,
        require_target: bool = True,
        verification_target: bool = False,
    ) -> None:
        rule = self._profiles.ax_rule(bundle_id, capability)
        self._profiles.authorize_ax(
            bundle_id,
            capability,
            tool_name=tool_name or rule.tool_name,
            identifier=identifier,
            role=role,
            action=action,
            verifier=verifier,
            allow_experimental=False,
            resolved_target=resolved_target,
            require_target=require_target,
            verification_target=verification_target,
        )

    def _reference(self, element: AXElementSnapshot) -> AXElementReference:
        return AXElementReference(
            application_bundle_id=element.application_bundle_id,
            window_identifier=element.window_identifier,
            reference_id=element.reference_id,
            identifier=element.identifier,
            role=element.role,
            parent_path=element.parent_path,
            captured_at=element.captured_at,
            expires_at=element.captured_at + timedelta(seconds=2),
        )

    def _action_result(self, element: AXElementSnapshot, detail: str) -> AXActionResult:
        return AXActionResult(
            performed=True,
            target=self._reference(element),
            observed_at=self.now(),
            detail=detail,
        )


def default_ax_controller() -> AXController:
    permissions = default_ax_permission_service()
    return AXController(
        RealSemanticAXAdapter(permissions),
        permissions,
        build_default_application_profiles(),
        app_control=default_app_control(),
    )
