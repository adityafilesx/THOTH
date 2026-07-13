"""Capability, permission, resolution, and mutation boundary for AX tools."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from thoth_daemon.core.application_profiles import (
    ApplicationProfileRegistry,
    build_default_application_profiles,
)
from thoth_daemon.core.ax_resolver import AXResolutionResult, AXResolver
from thoth_daemon.macos.app_control import AppControl, default_app_control
from thoth_daemon.macos.ax_permission import (
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
    AXVerificationRequest,
    AXVerificationResult,
    AXWindowSnapshot,
)


class AXController:
    def __init__(
        self,
        adapter: SemanticAXAdapter,
        permissions: AXPermissionService,
        profiles: ApplicationProfileRegistry,
        resolver: AXResolver | None = None,
        clock: Callable[[], datetime] | None = None,
        app_control: AppControl | None = None,
    ) -> None:
        self._adapter = adapter
        self._permissions = permissions
        self._profiles = profiles
        self._resolver = resolver or AXResolver()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._app_control = app_control

    def now(self) -> datetime:
        return self._clock()

    def inspect_application(self, bundle_id: str, capability: str) -> AXApplicationSnapshot:
        self._authorize(bundle_id, capability)
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
    ) -> AXWindowSnapshot | None:
        self._authorize(bundle_id, capability)
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
    ) -> AXResolutionResult:
        self._authorize(bundle_id, capability)
        if query.application_bundle_id != bundle_id:
            raise RuntimeError("AX query bundle does not match the approved bundle")
        self._permissions.require_granted(now=self.now())
        snapshot = self._adapter.inspect_application(bundle_id)
        elements = [element for window in snapshot.windows for element in window.elements]
        return self._resolver.resolve(
            query,
            elements,
            now=self.now(),
            capability_authorized=True,
            require_enabled=require_enabled,
        )

    def preview_action(
        self,
        bundle_id: str,
        capability: str,
        query: AXElementQuery,
        *,
        expected_current_value: AXPrimitive | None = None,
    ) -> AXActionResult:
        element = self._require_element(
            bundle_id,
            capability,
            query,
            expected_current_value=expected_current_value,
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
    ) -> AXActionResult:
        element = self._require_element(
            bundle_id,
            capability,
            query,
            expected_current_value=expected_current_value,
        )
        self._permissions.require_granted(now=self.now())
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
    ) -> AXActionResult:
        element = self._require_element(
            bundle_id,
            capability,
            query,
            expected_current_value=expected_current_value,
        )
        if action_name not in element.supported_actions:
            raise RuntimeError(
                f"AX action {action_name!r} is not supported by the resolved element"
            )
        self._permissions.require_granted(now=self.now())
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
    ) -> AXActionResult:
        element = self._require_element(
            bundle_id,
            capability,
            query,
            expected_current_value=expected_current_value,
        )
        self._permissions.require_granted(now=self.now())
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

        return AXVerifierDispatcher(self, self._app_control).verify(request, capability)

    def _require_element(
        self,
        bundle_id: str,
        capability: str,
        query: AXElementQuery,
        *,
        expected_current_value: AXPrimitive | None,
    ) -> AXElementSnapshot:
        result = self.resolve(
            bundle_id,
            capability,
            query,
            require_enabled=True,
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

    def _authorize(self, bundle_id: str, capability: str) -> None:
        self._profiles.authorize(bundle_id, capability, allow_experimental=False)

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
