"""macOS Accessibility (AX) adapter (Phase 4 slice 3).

Elements are addressed by ROLE + LABEL (AXRole and AXTitle/AXDescription),
never screen coordinates, so plans stay meaningful across window layouts.

``RealAXAdapter`` drives AXUIElement via PyObjC/ApplicationServices and is
**pending live verification**: it requires the Accessibility permission
(TCC) which this environment does not have. Every real operation first
checks ``AXIsProcessTrusted`` and raises ``AXPermissionError`` when the
permission is missing — a missing permission is a clean, typed failure,
never a fake success. ``MockAXAdapter`` is a deterministic in-memory tree
used by all unit tests.

Values read from AX elements are EXTERNAL, UNTRUSTED content: they are
returned as plain data and can never change objectives, approve actions,
or expand permissions.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class AXPermissionError(Exception):
    """Accessibility (TCC) permission is not granted to this process."""


@dataclass(frozen=True)
class AXElementInfo:
    role: str
    label: str
    value: str | None
    enabled: bool


class AXAdapter(Protocol):
    def list_elements(self, app_name: str) -> list[AXElementInfo]: ...
    def find_element(self, app_name: str, role: str, label: str) -> AXElementInfo | None: ...
    def read_value(self, app_name: str, role: str, label: str) -> str | None: ...
    def set_value(self, app_name: str, role: str, label: str, value: str) -> bool: ...
    def perform_action(self, app_name: str, role: str, label: str, action: str) -> bool: ...
    def wait_for_element(
        self, app_name: str, role: str, label: str, timeout_s: float
    ) -> AXElementInfo | None: ...


class RealAXAdapter:
    """AXUIElement-backed adapter. Pending live verification (needs the
    Accessibility TCC permission). Lazy PyObjC imports keep the daemon
    importable on machines without the frameworks."""

    def __init__(self, trust_probe: Callable[[], bool] | None = None) -> None:
        self._trust_probe = trust_probe

    # -- permission gate --------------------------------------------------
    def is_trusted(self) -> bool:
        if self._trust_probe is not None:
            return self._trust_probe()
        from ApplicationServices import AXIsProcessTrusted  # type: ignore[import-not-found]

        return bool(AXIsProcessTrusted())

    def _require_trust(self) -> None:
        if not self.is_trusted():
            raise AXPermissionError(
                "Accessibility permission not granted. Enable it in System Settings "
                "> Privacy & Security > Accessibility (pending live verification)."
            )

    # -- element access ----------------------------------------------------
    def _app_element(self, app_name: str) -> Any:
        from AppKit import NSWorkspace  # type: ignore[import-untyped]
        from ApplicationServices import AXUIElementCreateApplication

        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.localizedName() and str(app.localizedName()) == app_name:
                return AXUIElementCreateApplication(app.processIdentifier())
        return None

    def _walk(self, element: Any, out: list[AXElementInfo], depth: int = 0) -> None:
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
        )

        if depth > 12:  # bounded traversal
            return

        def attr(name: str) -> Any:
            err, value = AXUIElementCopyAttributeValue(element, name, None)
            return value if err == 0 else None

        role = attr("AXRole")
        label = attr("AXTitle") or attr("AXDescription") or attr("AXIdentifier")
        value = attr("AXValue")
        enabled = attr("AXEnabled")
        if role and label:
            out.append(
                AXElementInfo(
                    role=str(role),
                    label=str(label),
                    value=str(value) if value is not None else None,
                    enabled=bool(enabled) if enabled is not None else True,
                )
            )
        children = attr("AXChildren") or []
        for child in children:
            self._walk(child, out, depth + 1)

    def list_elements(self, app_name: str) -> list[AXElementInfo]:
        self._require_trust()
        app = self._app_element(app_name)
        if app is None:
            return []
        out: list[AXElementInfo] = []
        self._walk(app, out)
        return out

    def find_element(self, app_name: str, role: str, label: str) -> AXElementInfo | None:
        for element in self.list_elements(app_name):
            if element.role == role and element.label == label:
                return element
        return None

    def read_value(self, app_name: str, role: str, label: str) -> str | None:
        element = self.find_element(app_name, role, label)
        return element.value if element else None

    def _raw_find(self, app_name: str, role: str, label: str) -> Any:
        from ApplicationServices import AXUIElementCopyAttributeValue

        def attr(el: Any, name: str) -> Any:
            err, value = AXUIElementCopyAttributeValue(el, name, None)
            return value if err == 0 else None

        def walk(el: Any, depth: int = 0) -> Any:
            if depth > 12:
                return None
            el_role = attr(el, "AXRole")
            el_label = attr(el, "AXTitle") or attr(el, "AXDescription") or attr(el, "AXIdentifier")
            if el_role and str(el_role) == role and el_label and str(el_label) == label:
                return el
            for child in attr(el, "AXChildren") or []:
                found = walk(child, depth + 1)
                if found is not None:
                    return found
            return None

        app = self._app_element(app_name)
        return walk(app) if app is not None else None

    def set_value(self, app_name: str, role: str, label: str, value: str) -> bool:
        self._require_trust()
        from ApplicationServices import AXUIElementSetAttributeValue

        raw = self._raw_find(app_name, role, label)
        if raw is None:
            return False
        return bool(AXUIElementSetAttributeValue(raw, "AXValue", value) == 0)

    def perform_action(self, app_name: str, role: str, label: str, action: str) -> bool:
        self._require_trust()
        from ApplicationServices import AXUIElementPerformAction

        raw = self._raw_find(app_name, role, label)
        if raw is None:
            return False
        return bool(AXUIElementPerformAction(raw, action) == 0)

    def wait_for_element(
        self, app_name: str, role: str, label: str, timeout_s: float
    ) -> AXElementInfo | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            element = self.find_element(app_name, role, label)
            if element is not None:
                return element
            time.sleep(0.1)
        return None


@dataclass
class MockAXAdapter:
    """Deterministic in-memory AX tree. MOCK — used by unit tests and by
    environments without the Accessibility permission."""

    tree: dict[str, list[AXElementInfo]] = field(default_factory=dict)
    actions_performed: list[tuple[str, str, str, str]] = field(default_factory=list)

    def __init__(self, tree: dict[str, list[AXElementInfo]] | None = None) -> None:
        self.tree = tree or {}
        self.actions_performed = []
        self._pending: list[tuple[str, AXElementInfo, int]] = []

    # -- test priming ------------------------------------------------------
    def appear_after(self, app_name: str, element: AXElementInfo, polls: int) -> None:
        """Make ``element`` appear in ``app_name`` after N find polls."""
        self._pending.append((app_name, element, polls))

    def _tick_pending(self, app_name: str) -> None:
        remaining: list[tuple[str, AXElementInfo, int]] = []
        for app, element, polls in self._pending:
            if app == app_name and polls <= 1:
                self.tree.setdefault(app, []).append(element)
            elif app == app_name:
                remaining.append((app, element, polls - 1))
            else:
                remaining.append((app, element, polls))
        self._pending = remaining

    # -- adapter ops ---------------------------------------------------------
    def list_elements(self, app_name: str) -> list[AXElementInfo]:
        return list(self.tree.get(app_name, []))

    def find_element(self, app_name: str, role: str, label: str) -> AXElementInfo | None:
        self._tick_pending(app_name)
        for element in self.list_elements(app_name):
            if element.role == role and element.label == label:
                return element
        return None

    def read_value(self, app_name: str, role: str, label: str) -> str | None:
        element = self.find_element(app_name, role, label)
        return element.value if element else None

    def set_value(self, app_name: str, role: str, label: str, value: str) -> bool:
        elements = self.tree.get(app_name, [])
        for i, element in enumerate(elements):
            if element.role == role and element.label == label:
                if not element.enabled:
                    return False
                elements[i] = AXElementInfo(
                    role=element.role, label=element.label, value=value, enabled=element.enabled
                )
                return True
        return False

    def perform_action(self, app_name: str, role: str, label: str, action: str) -> bool:
        element = self.find_element(app_name, role, label)
        if element is None or not element.enabled:
            return False
        self.actions_performed.append((app_name, role, label, action))
        return True

    def wait_for_element(
        self, app_name: str, role: str, label: str, timeout_s: float
    ) -> AXElementInfo | None:
        deadline = time.monotonic() + timeout_s
        while True:
            element = self.find_element(app_name, role, label)
            if element is not None:
                return element
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.01)


def default_ax_adapter() -> AXAdapter:
    """Real adapter by default; callers (and tests) inject mocks."""
    return RealAXAdapter()
