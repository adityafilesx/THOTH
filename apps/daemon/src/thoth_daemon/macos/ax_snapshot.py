"""Bounded conversion of raw AX observations into redacted snapshots."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from thoth_daemon.core.foreground import ForegroundRedactor
from thoth_daemon.schemas.ax import (
    AXElementSnapshot,
    AXValueKind,
    AXValueMetadata,
    AXWindowSnapshot,
)


@dataclass(frozen=True)
class AXSnapshotLimits:
    max_depth: int = 12
    max_elements: int = 500
    max_string_bytes: int = 4096
    max_actions: int = 32

    def __post_init__(self) -> None:
        if min(self.max_depth, self.max_elements, self.max_string_bytes, self.max_actions) <= 0:
            raise ValueError("all AX snapshot limits must be positive")
        if self.max_depth > 12 or self.max_elements > 500 or self.max_string_bytes > 4096:
            raise ValueError("AX snapshot limits cannot exceed the safety ceiling")


@dataclass
class AXObservedNode:
    role: str
    subrole: str | None = None
    identifier: str | None = None
    label: str | None = None
    description: str | None = None
    value: Any = None
    enabled: bool | None = None
    focused: bool | None = None
    selected: bool | None = None
    visible: bool | None = None
    supported_actions: list[str] = field(default_factory=list)
    children: list[AXObservedNode] = field(default_factory=list)
    hidden_system: bool = False


def bounded_text(value: str, *, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    marker = "…"
    marker_bytes = marker.encode("utf-8")
    if max_bytes < len(marker_bytes):
        return encoded[:max_bytes].decode("utf-8", errors="ignore"), True
    prefix = encoded[: max_bytes - len(marker_bytes)].decode("utf-8", errors="ignore")
    return prefix + marker, True


def build_window_snapshot(
    *,
    application_bundle_id: str,
    window_identifier: str | None,
    window_title: str | None,
    focused: bool | None,
    roots: list[AXObservedNode],
    captured_at: datetime,
    limits: AXSnapshotLimits | None = None,
) -> AXWindowSnapshot:
    budget = limits or AXSnapshotLimits()
    redactor = ForegroundRedactor()
    title = redactor.redact_title(window_title) if window_title is not None else None
    title, title_truncated = (
        bounded_text(title, max_bytes=budget.max_string_bytes)
        if title is not None
        else (None, False)
    )

    elements: list[AXElementSnapshot] = []
    visited: set[int] = set()
    collection_truncated = title_truncated

    def visit(node: AXObservedNode, depth: int, parent_path: tuple[str, ...]) -> None:
        nonlocal collection_truncated
        if node.hidden_system:
            return
        if depth > budget.max_depth or len(elements) >= budget.max_elements:
            collection_truncated = True
            return
        identity = id(node)
        if identity in visited:
            collection_truncated = True
            return
        visited.add(identity)

        role, role_truncated = bounded_text(str(node.role), max_bytes=budget.max_string_bytes)
        subrole, subrole_truncated = _optional_text(node.subrole, budget)
        identifier, identifier_truncated = _optional_text(node.identifier, budget)
        label, label_truncated = _optional_text(node.label, budget)
        description, description_truncated = _optional_text(node.description, budget)
        actions = tuple(node.supported_actions[: budget.max_actions])
        action_truncated = len(node.supported_actions) > budget.max_actions
        element_truncated = any(
            (
                role_truncated,
                subrole_truncated,
                identifier_truncated,
                label_truncated,
                description_truncated,
                action_truncated,
            )
        )
        value_metadata = _value_metadata(node, budget)
        token = identifier or label or role
        reference_material = "|".join(
            (
                application_bundle_id,
                window_identifier or "",
                captured_at.isoformat(),
                str(len(elements)),
                *parent_path,
                token,
            )
        )
        reference_id = hashlib.sha256(reference_material.encode()).hexdigest()[:32]
        elements.append(
            AXElementSnapshot(
                reference_id=reference_id,
                application_bundle_id=application_bundle_id,
                window_identifier=window_identifier,
                window_title=title,
                role=role,
                subrole=subrole,
                identifier=identifier,
                label=label,
                description=description,
                value_metadata=value_metadata,
                enabled=node.enabled,
                focused=node.focused,
                selected=node.selected,
                visible=node.visible,
                child_count=len(node.children),
                supported_actions=actions,
                parent_path=parent_path,
                captured_at=captured_at,
                truncated=element_truncated or bool(value_metadata and value_metadata.truncated),
            )
        )
        if element_truncated:
            collection_truncated = True

        next_path = (*parent_path, token)
        for child in node.children:
            visit(child, depth + 1, next_path)

    for root in roots:
        visit(root, 0, ())

    return AXWindowSnapshot(
        application_bundle_id=application_bundle_id,
        identifier=window_identifier,
        title=title,
        focused=focused,
        element_count=len(elements),
        elements=tuple(elements),
        captured_at=captured_at,
        truncated=collection_truncated,
    )


def _optional_text(value: str | None, limits: AXSnapshotLimits) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    return bounded_text(str(value), max_bytes=limits.max_string_bytes)


def _value_metadata(node: AXObservedNode, limits: AXSnapshotLimits) -> AXValueMetadata | None:
    if node.value is None:
        return None
    sensitive_description = " ".join(
        part.lower() for part in (node.identifier, node.label, node.description) if part
    )
    sensitive = node.role == "AXSecureTextField" or any(
        marker in sensitive_description
        for marker in ("password", "passcode", "one-time", "verification code", "otp", "token")
    )
    kind = _value_kind(node.value)
    if sensitive or kind is AXValueKind.UNSUPPORTED:
        return AXValueMetadata(
            kind=kind,
            value=None,
            redacted=True,
            length=len(node.value) if isinstance(node.value, str) else None,
        )
    if isinstance(node.value, str):
        value, truncated = bounded_text(node.value, max_bytes=limits.max_string_bytes)
        return AXValueMetadata(
            kind=kind,
            value=value,
            length=len(node.value),
            truncated=truncated,
        )
    return AXValueMetadata(kind=kind, value=node.value)


def _value_kind(value: Any) -> AXValueKind:
    if isinstance(value, str):
        return AXValueKind.STRING
    if isinstance(value, bool):
        return AXValueKind.BOOLEAN
    if isinstance(value, int):
        return AXValueKind.INTEGER
    if isinstance(value, float):
        return AXValueKind.NUMBER
    return AXValueKind.UNSUPPORTED
