"""Semantic AX adapter boundary and deterministic in-memory mock."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from omnimac_daemon.macos.ax_permission import (
    AXPermissionService,
    default_ax_permission_service,
)
from omnimac_daemon.macos.ax_snapshot import (
    AXObservedNode,
    AXSnapshotLimits,
    build_window_snapshot,
)
from omnimac_daemon.schemas.ax import (
    AXApplicationSnapshot,
    AXElementSnapshot,
    AXPrimitive,
    AXValueKind,
    AXValueMetadata,
    AXWindowSnapshot,
)


class SemanticAXAdapter(Protocol):
    def inspect_application(self, bundle_id: str) -> AXApplicationSnapshot: ...
    def inspect_window(self, bundle_id: str, window_identifier: str) -> AXWindowSnapshot | None: ...
    def set_value(self, element: AXElementSnapshot, value: AXPrimitive) -> bool: ...
    def perform_action(self, element: AXElementSnapshot, action_name: str) -> bool: ...
    def select_option(self, element: AXElementSnapshot, option: str) -> bool: ...


class RealSemanticAXAdapter:
    """Bounded AXUIElement adapter addressed by bundle id and semantics."""

    def __init__(
        self,
        permissions: AXPermissionService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._permissions = permissions or default_ax_permission_service()
        self._clock = clock or (lambda: datetime.now(UTC))

    def inspect_application(self, bundle_id: str) -> AXApplicationSnapshot:
        self._permissions.require_granted(now=self._clock())
        running = self._running_application(bundle_id)
        if running is None:
            raise RuntimeError(f"application {bundle_id!r} is not running")
        application = self._application_element(running)
        captured_at = self._clock()
        raw_windows, windows_truncated = self._attribute_values(application, "AXWindows", 20)
        windows: list[AXWindowSnapshot] = []
        total_elements = 0
        truncated = windows_truncated
        for index, raw_window in enumerate(raw_windows):
            if total_elements >= 500:
                truncated = True
                break
            title = self._text_attribute(raw_window, "AXTitle")
            identifier = self._text_attribute(raw_window, "AXIdentifier") or f"window-{index}"
            focused = self._bool_attribute(raw_window, "AXFocused")
            remaining = 500 - total_elements
            roots, raw_truncated = self._observed_roots(raw_window, remaining)
            window = build_window_snapshot(
                application_bundle_id=bundle_id,
                window_identifier=identifier,
                window_title=title,
                focused=focused,
                roots=roots,
                captured_at=captured_at,
                limits=AXSnapshotLimits(max_elements=remaining),
            )
            total_elements += window.element_count
            truncated = truncated or raw_truncated or window.truncated
            windows.append(window)
        return AXApplicationSnapshot(
            bundle_id=bundle_id,
            display_name=str(running.localizedName() or bundle_id),
            process_identifier=int(running.processIdentifier()),
            windows=tuple(windows),
            captured_at=captured_at,
            truncated=truncated,
        )

    def inspect_window(self, bundle_id: str, window_identifier: str) -> AXWindowSnapshot | None:
        application = self.inspect_application(bundle_id)
        return next(
            (window for window in application.windows if window.identifier == window_identifier),
            None,
        )

    def set_value(self, element: AXElementSnapshot, value: AXPrimitive) -> bool:
        self._permissions.require_granted(now=self._clock())
        raw = self._find_raw(element)
        if raw is None:
            return False
        from ApplicationServices import (  # type: ignore[import-untyped]
            AXUIElementSetAttributeValue,
        )

        return bool(AXUIElementSetAttributeValue(raw, "AXValue", value) == 0)

    def perform_action(self, element: AXElementSnapshot, action_name: str) -> bool:
        self._permissions.require_granted(now=self._clock())
        raw = self._find_raw(element)
        if raw is None:
            return False
        from ApplicationServices import AXUIElementPerformAction

        return bool(AXUIElementPerformAction(raw, action_name) == 0)

    def select_option(self, element: AXElementSnapshot, option: str) -> bool:
        self._permissions.require_granted(now=self._clock())
        raw = self._find_raw(element)
        if raw is None:
            return False
        from ApplicationServices import AXUIElementPerformAction, AXUIElementSetAttributeValue

        if AXUIElementSetAttributeValue(raw, "AXValue", option) == 0:
            return True
        for child in self._bounded_descendants(raw, 100):
            if self._text_attribute(child, "AXTitle") == option:
                return bool(AXUIElementPerformAction(child, "AXPress") == 0)
        return False

    def _running_application(self, bundle_id: str) -> Any:
        from AppKit import NSWorkspace  # type: ignore[import-untyped]

        return next(
            (app for app in NSWorkspace.sharedWorkspace().runningApplications() if str(app.bundleIdentifier() or "") == bundle_id),
            None,
        )

    @staticmethod
    def _application_element(running: Any) -> Any:
        from ApplicationServices import AXUIElementCreateApplication

        return AXUIElementCreateApplication(running.processIdentifier())

    def _observed_roots(
        self,
        raw_window: Any,
        limit: int,
    ) -> tuple[list[AXObservedNode], bool]:
        raw_children, children_truncated = self._attribute_values(raw_window, "AXChildren", limit)
        visited: set[int] = set()
        count = [0]
        truncated = [children_truncated]
        roots: list[AXObservedNode] = []
        for child in raw_children:
            observed = self._observed_node(child, 0, limit, visited, count, truncated)
            if observed is not None:
                roots.append(observed)
        return roots, truncated[0]

    def _observed_node(
        self,
        raw: Any,
        depth: int,
        limit: int,
        visited: set[int],
        count: list[int],
        truncated: list[bool],
    ) -> AXObservedNode | None:
        identity = id(raw)
        if identity in visited or depth > 12 or count[0] >= limit:
            truncated[0] = True
            return None
        visited.add(identity)
        count[0] += 1
        role = self._text_attribute(raw, "AXRole")
        if role is None:
            return None
        identifier = self._text_attribute(raw, "AXIdentifier")
        label = self._text_attribute(raw, "AXTitle")
        description = self._text_attribute(raw, "AXDescription")
        sensitive = _sensitive_semantics(role, identifier, label, description)
        value = None if sensitive else self._attribute(raw, "AXValue")
        child_budget = max(0, limit - count[0])
        raw_children, children_truncated = self._attribute_values(raw, "AXChildren", child_budget)
        truncated[0] = truncated[0] or children_truncated
        children: list[AXObservedNode] = []
        for child in raw_children:
            observed = self._observed_node(
                child,
                depth + 1,
                limit,
                visited,
                count,
                truncated,
            )
            if observed is not None:
                children.append(observed)
        hidden = self._bool_attribute(raw, "AXHidden")
        return AXObservedNode(
            role=role,
            subrole=self._text_attribute(raw, "AXSubrole"),
            identifier=identifier,
            label=label,
            description=description,
            value=value,
            enabled=self._bool_attribute(raw, "AXEnabled"),
            focused=self._bool_attribute(raw, "AXFocused"),
            selected=self._bool_attribute(raw, "AXSelected"),
            visible=None if hidden is None else not hidden,
            supported_actions=self._actions(raw),
            children=children,
        )

    def _find_raw(self, element: AXElementSnapshot) -> Any:
        running = self._running_application(element.application_bundle_id)
        if running is None:
            return None
        application = self._application_element(running)
        raw_windows, _ = self._attribute_values(application, "AXWindows", 20)
        matches: list[Any] = []
        inspected = 0
        stack: list[tuple[Any, int]] = [(window, 0) for window in raw_windows]
        visited: set[int] = set()
        while stack and inspected < 500 and len(matches) < 2:
            raw, depth = stack.pop()
            identity = id(raw)
            if identity in visited or depth > 12:
                continue
            visited.add(identity)
            inspected += 1
            if self._raw_matches(raw, element):
                matches.append(raw)
            children, _ = self._attribute_values(raw, "AXChildren", 500 - inspected)
            stack.extend((child, depth + 1) for child in reversed(children))
        return matches[0] if len(matches) == 1 else None

    def _raw_matches(self, raw: Any, element: AXElementSnapshot) -> bool:
        role = self._text_attribute(raw, "AXRole")
        if role != element.role:
            return False
        identifier = self._text_attribute(raw, "AXIdentifier")
        if element.identifier is not None:
            return identifier == element.identifier
        label = self._text_attribute(raw, "AXTitle") or self._text_attribute(raw, "AXDescription")
        return label == (element.label or element.description)

    def _bounded_descendants(self, raw: Any, limit: int) -> list[Any]:
        out: list[Any] = []
        stack = [raw]
        visited: set[int] = set()
        while stack and len(out) < limit:
            current = stack.pop()
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            out.append(current)
            children, _ = self._attribute_values(current, "AXChildren", limit - len(out))
            stack.extend(reversed(children))
        return out

    @staticmethod
    def _attribute(raw: Any, name: str) -> Any:
        from ApplicationServices import AXUIElementCopyAttributeValue

        error, value = AXUIElementCopyAttributeValue(raw, name, None)
        return value if error == 0 else None

    def _text_attribute(self, raw: Any, name: str) -> str | None:
        value = self._attribute(raw, name)
        return str(value) if value is not None else None

    def _bool_attribute(self, raw: Any, name: str) -> bool | None:
        value = self._attribute(raw, name)
        return bool(value) if value is not None else None

    @staticmethod
    def _attribute_values(raw: Any, name: str, limit: int) -> tuple[list[Any], bool]:
        if limit <= 0:
            return [], True
        from ApplicationServices import (
            AXUIElementCopyAttributeValues,
            AXUIElementGetAttributeValueCount,
        )

        count_error, count = AXUIElementGetAttributeValueCount(raw, name, None)
        if count_error != 0:
            return [], False
        bounded_count = min(int(count), limit)
        values_error, values = AXUIElementCopyAttributeValues(raw, name, 0, bounded_count, None)
        if values_error != 0 or values is None:
            return [], False
        return list(values), int(count) > bounded_count

    @staticmethod
    def _actions(raw: Any) -> list[str]:
        from ApplicationServices import AXUIElementCopyActionNames

        error, actions = AXUIElementCopyActionNames(raw, None)
        if error != 0 or actions is None:
            return []
        return [str(action) for action in list(actions)[:32]]


class MockSemanticAXAdapter:
    """Mutable semantic fixture. MOCK — no OS or TCC interaction."""

    def __init__(self, applications: Sequence[AXApplicationSnapshot]) -> None:
        self._applications = {application.bundle_id: application for application in applications}
        self.mutations: list[tuple[str, str, AXPrimitive]] = []

    @classmethod
    def from_windows(
        cls,
        *,
        bundle_id: str,
        display_name: str,
        process_identifier: int,
        windows: list[AXWindowSnapshot],
        captured_at: datetime,
    ) -> MockSemanticAXAdapter:
        return cls(
            [
                AXApplicationSnapshot(
                    bundle_id=bundle_id,
                    display_name=display_name,
                    process_identifier=process_identifier,
                    windows=windows,
                    captured_at=captured_at,
                )
            ]
        )

    def inspect_application(self, bundle_id: str) -> AXApplicationSnapshot:
        application = self._applications.get(bundle_id)
        if application is None:
            raise RuntimeError(f"application {bundle_id!r} is not available")
        return application

    def inspect_window(self, bundle_id: str, window_identifier: str) -> AXWindowSnapshot | None:
        application = self.inspect_application(bundle_id)
        return next(
            (window for window in application.windows if window.identifier == window_identifier),
            None,
        )

    def set_value(self, element: AXElementSnapshot, value: AXPrimitive) -> bool:
        if element.enabled is not True:
            return False
        self.mutations.append(("set_value", element.reference_id, value))
        return self._replace_value(element, value)

    def perform_action(self, element: AXElementSnapshot, action_name: str) -> bool:
        if element.enabled is not True or action_name not in element.supported_actions:
            return False
        self.mutations.append(("perform_action", element.reference_id, action_name))
        return True

    def select_option(self, element: AXElementSnapshot, option: str) -> bool:
        if element.enabled is not True:
            return False
        self.mutations.append(("select_option", element.reference_id, option))
        return self._replace_value(element, option)

    def replace_application(self, application: AXApplicationSnapshot) -> None:
        self._applications[application.bundle_id] = application

    def _replace_value(self, target: AXElementSnapshot, value: AXPrimitive) -> bool:
        application = self._applications.get(target.application_bundle_id)
        if application is None:
            return False
        found = False
        windows: list[AXWindowSnapshot] = []
        for window in application.windows:
            elements: list[AXElementSnapshot] = []
            for element in window.elements:
                if element.reference_id == target.reference_id:
                    found = True
                    elements.append(element.model_copy(update={"value_metadata": _metadata(value)}))
                else:
                    elements.append(element)
            windows.append(window.model_copy(update={"elements": tuple(elements)}))
        if found:
            self._applications[target.application_bundle_id] = application.model_copy(update={"windows": tuple(windows)})
        return found


def _metadata(value: AXPrimitive) -> AXValueMetadata:
    if isinstance(value, str):
        return AXValueMetadata(kind=AXValueKind.STRING, value=value, length=len(value))
    if isinstance(value, bool):
        return AXValueMetadata(kind=AXValueKind.BOOLEAN, value=value)
    if isinstance(value, int):
        return AXValueMetadata(kind=AXValueKind.INTEGER, value=value)
    return AXValueMetadata(kind=AXValueKind.NUMBER, value=value)


def _sensitive_semantics(
    role: str,
    identifier: str | None,
    label: str | None,
    description: str | None,
) -> bool:
    semantics = " ".join(part.lower() for part in (identifier, label, description) if part is not None)
    return role == "AXSecureTextField" or any(
        marker in semantics for marker in ("password", "passcode", "one-time", "verification code", "otp", "token")
    )
