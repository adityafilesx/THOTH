"""macOS Accessibility tools (Phase 4 slice 3).

Six tools over an injected AXAdapter, addressing elements by ROLE + LABEL
(never coordinates). Reads are R0; element mutation (set value / perform
action) is R1, dry-run safe, and self-checked: a set that does not stick
reports verified=False, and independent verification uses the
ACCESSIBILITY_VALUE verifier (core/verifiers). All tools declare
requested_scope(apps=[app]) so the ScopeEnforcer refuses apps outside the
workspace's approved list. AX values are UNTRUSTED external content —
returned as plain data only. The real adapter requires the Accessibility
TCC permission (pending live verification); a missing permission raises a
typed AXPermissionError which surfaces as a clean tool failure.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from thoth_daemon.macos.ax import AXAdapter, default_ax_adapter
from thoth_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from thoth_daemon.tools.base import ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AXElement(_Out):
    role: str
    label: str
    value: str | None
    enabled: bool


def _element(info: object) -> AXElement:
    return AXElement(
        role=info.role,  # type: ignore[attr-defined]
        label=info.label,  # type: ignore[attr-defined]
        value=info.value,  # type: ignore[attr-defined]
        enabled=info.enabled,  # type: ignore[attr-defined]
    )


class _AppScoped(_In):
    app: str


class _ElementRef(_AppScoped):
    role: str
    label: str


# -- ax_inspect_application (R0) ------------------------------------------
class AXInspectIn(_AppScoped):
    pass


class AXInspectOut(_Out):
    app: str
    elements: list[AXElement]


class AXInspectApplication(ToolDefinition[AXInspectIn, AXInspectOut]):
    name = "ax_inspect_application"
    description = "List the accessibility elements (role/label/value) of an approved app."
    input_model = AXInspectIn
    output_model = AXInspectOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def __init__(self, adapter: AXAdapter | None = None) -> None:
        super().__init__()
        self._ax = adapter or default_ax_adapter()

    def requested_scope(self, args: AXInspectIn) -> ResourceScope:
        return ResourceScope(apps=[args.app])

    async def run(self, args: AXInspectIn, dry_run: bool) -> AXInspectOut:
        return AXInspectOut(
            app=args.app, elements=[_element(e) for e in self._ax.list_elements(args.app)]
        )


# -- ax_find_element (R0) ---------------------------------------------------
class AXFindIn(_ElementRef):
    pass


class AXFindOut(_Out):
    found: bool
    element: AXElement | None


class AXFindElement(ToolDefinition[AXFindIn, AXFindOut]):
    name = "ax_find_element"
    description = "Find an element by role + label in an approved app."
    input_model = AXFindIn
    output_model = AXFindOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def __init__(self, adapter: AXAdapter | None = None) -> None:
        super().__init__()
        self._ax = adapter or default_ax_adapter()

    def requested_scope(self, args: AXFindIn) -> ResourceScope:
        return ResourceScope(apps=[args.app])

    async def run(self, args: AXFindIn, dry_run: bool) -> AXFindOut:
        info = self._ax.find_element(args.app, args.role, args.label)
        return AXFindOut(found=info is not None, element=_element(info) if info else None)


# -- ax_read_value (R0) -------------------------------------------------------
class AXReadIn(_ElementRef):
    pass


class AXReadOut(_Out):
    value: str | None


class AXReadValue(ToolDefinition[AXReadIn, AXReadOut]):
    name = "ax_read_value"
    description = "Read an element's value (untrusted external content)."
    input_model = AXReadIn
    output_model = AXReadOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def __init__(self, adapter: AXAdapter | None = None) -> None:
        super().__init__()
        self._ax = adapter or default_ax_adapter()

    def requested_scope(self, args: AXReadIn) -> ResourceScope:
        return ResourceScope(apps=[args.app])

    async def run(self, args: AXReadIn, dry_run: bool) -> AXReadOut:
        return AXReadOut(value=self._ax.read_value(args.app, args.role, args.label))


# -- ax_wait_for_element (R0) --------------------------------------------------
class AXWaitIn(_ElementRef):
    timeout_s: float = Field(default=5.0, gt=0, le=30)


class AXWaitOut(_Out):
    found: bool
    element: AXElement | None


class AXWaitForElement(ToolDefinition[AXWaitIn, AXWaitOut]):
    name = "ax_wait_for_element"
    description = "Wait (bounded) for an element to appear by role + label."
    input_model = AXWaitIn
    output_model = AXWaitOut
    default_risk = RiskLevel.R0
    timeout_s = 35.0
    verification = VerificationStrategy.NONE_READONLY

    def __init__(self, adapter: AXAdapter | None = None) -> None:
        super().__init__()
        self._ax = adapter or default_ax_adapter()

    def requested_scope(self, args: AXWaitIn) -> ResourceScope:
        return ResourceScope(apps=[args.app])

    async def run(self, args: AXWaitIn, dry_run: bool) -> AXWaitOut:
        info = self._ax.wait_for_element(args.app, args.role, args.label, args.timeout_s)
        return AXWaitOut(found=info is not None, element=_element(info) if info else None)


# -- ax_set_value (R1) ----------------------------------------------------------
class AXSetIn(_ElementRef):
    value: str


class AXSetOut(_Out):
    set: bool
    verified: bool


class AXSetValue(ToolDefinition[AXSetIn, AXSetOut]):
    name = "ax_set_value"
    description = "Set an element's value in an approved app (role/label addressed)."
    input_model = AXSetIn
    output_model = AXSetOut
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE
    redaction_fields: ClassVar[list[str]] = ["value"]

    def __init__(self, adapter: AXAdapter | None = None) -> None:
        super().__init__()
        self._ax = adapter or default_ax_adapter()

    def requested_scope(self, args: AXSetIn) -> ResourceScope:
        return ResourceScope(apps=[args.app])

    async def run(self, args: AXSetIn, dry_run: bool) -> AXSetOut:
        if dry_run:
            return AXSetOut(set=False, verified=False)
        ok = self._ax.set_value(args.app, args.role, args.label, args.value)
        if not ok:
            raise RuntimeError(f"could not set value on {args.role}/{args.label} in {args.app}")
        # Self-check: re-read and compare. Independent verification uses the
        # ACCESSIBILITY_VALUE verifier on top of this.
        verified = self._ax.read_value(args.app, args.role, args.label) == args.value
        return AXSetOut(set=True, verified=verified)


# -- ax_perform_action (R1) -----------------------------------------------------
class AXActionIn(_ElementRef):
    action: str = Field(pattern=r"^AX[A-Za-z]+$")  # e.g. AXPress, AXConfirm


class AXActionOut(_Out):
    performed: bool


class AXPerformAction(ToolDefinition[AXActionIn, AXActionOut]):
    name = "ax_perform_action"
    description = "Perform a named AX action (e.g. AXPress) on an element."
    input_model = AXActionIn
    output_model = AXActionOut
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE

    def __init__(self, adapter: AXAdapter | None = None) -> None:
        super().__init__()
        self._ax = adapter or default_ax_adapter()

    def requested_scope(self, args: AXActionIn) -> ResourceScope:
        return ResourceScope(apps=[args.app])

    async def run(self, args: AXActionIn, dry_run: bool) -> AXActionOut:
        if dry_run:
            return AXActionOut(performed=False)
        ok = self._ax.perform_action(args.app, args.role, args.label, args.action)
        if not ok:
            raise RuntimeError(
                f"could not perform {args.action} on {args.role}/{args.label} in {args.app}"
            )
        return AXActionOut(performed=True)


def register_ax_tools(registry: ToolRegistry, adapter: AXAdapter | None = None) -> None:
    ax = adapter or default_ax_adapter()
    for tool in (
        AXInspectApplication(ax),
        AXFindElement(ax),
        AXReadValue(ax),
        AXWaitForElement(ax),
        AXSetValue(ax),
        AXPerformAction(ax),
    ):
        registry.register(tool)
