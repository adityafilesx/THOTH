"""macOS app-control tools (Phase 3 slice 6). Launch, focus, and list running
apps via an injected AppControl adapter (real NSWorkspace by default). Launch
and focus declare requested_scope(apps=[name]) so the slice-1 enforcer refuses
any app not in the workspace's approved_apps. No AX element interaction (TCC)."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict

from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.macos.app_control import AppControl, default_app_control
from thoth_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from thoth_daemon.tools.base import IndependentToolVerification, ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AppEntry(_Out):
    name: str
    bundle_id: str | None
    active: bool


class AppListIn(_In):
    pass


class AppListOut(_Out):
    running: list[AppEntry]


class AppList(ToolDefinition[AppListIn, AppListOut]):
    name = "app_list"
    description = "List running applications (read-only)."
    input_model = AppListIn
    output_model = AppListOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def __init__(self, adapter: AppControl | None = None) -> None:
        super().__init__()
        self._ac = adapter or default_app_control()

    async def run(self, args: AppListIn, dry_run: bool) -> AppListOut:
        return AppListOut(
            running=[
                AppEntry(name=a.name, bundle_id=a.bundle_id, active=a.active)
                for a in self._ac.list_running()
            ]
        )


class AppLaunchIn(_In):
    app: str


class AppLaunchOut(_Out):
    app: str
    launched: bool


class AppLaunch(ToolDefinition[AppLaunchIn, AppLaunchOut]):
    name = "app_launch"
    description = "Launch an approved application."
    focus_policy = FocusPolicy.KEEP_NEW_FOCUS
    input_model = AppLaunchIn
    output_model = AppLaunchOut
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE

    def __init__(self, adapter: AppControl | None = None) -> None:
        super().__init__()
        self._ac = adapter or default_app_control()

    def requested_scope(self, args: AppLaunchIn) -> ResourceScope:
        return ResourceScope(apps=[args.app])

    def focus_target(self, args: AppLaunchIn) -> str:
        return args.app

    async def run(self, args: AppLaunchIn, dry_run: bool) -> AppLaunchOut:
        if dry_run:
            return AppLaunchOut(app=args.app, launched=False)
        ok = self._ac.launch(args.app)
        if not ok or not await _wait_for_running(self._ac, args.app):
            raise RuntimeError(f"failed to launch {args.app}")
        if not self._ac.activate(args.app):
            raise RuntimeError(f"failed to activate {args.app} after launch")
        if not await _wait_for_frontmost(self._ac, args.app):
            raise RuntimeError(f"failed to focus {args.app} after launch")
        return AppLaunchOut(app=args.app, launched=True)

    def verify_independently(self, args: AppLaunchIn) -> IndependentToolVerification:
        running = any(
            app.name == args.app or app.bundle_id == args.app for app in self._ac.list_running()
        )
        return IndependentToolVerification(
            passed=running,
            detail=(
                f"application {args.app!r} is running"
                if running
                else f"application {args.app!r} is not running"
            ),
        )


class AppFocusIn(_In):
    app: str


class AppFocusOut(_Out):
    app: str
    focused: bool


class AppFocus(ToolDefinition[AppFocusIn, AppFocusOut]):
    name = "app_focus"
    description = "Bring an approved application to the front."
    focus_policy = FocusPolicy.KEEP_NEW_FOCUS
    input_model = AppFocusIn
    output_model = AppFocusOut
    default_risk = RiskLevel.R1
    verification = VerificationStrategy.STATE_PROBE

    def __init__(self, adapter: AppControl | None = None) -> None:
        super().__init__()
        self._ac = adapter or default_app_control()

    def requested_scope(self, args: AppFocusIn) -> ResourceScope:
        return ResourceScope(apps=[args.app])

    def focus_target(self, args: AppFocusIn) -> str:
        return args.app

    async def run(self, args: AppFocusIn, dry_run: bool) -> AppFocusOut:
        ok = self._ac.activate(args.app)
        if not ok or not await _wait_for_frontmost(self._ac, args.app):
            raise RuntimeError(f"failed to focus {args.app}")
        return AppFocusOut(app=args.app, focused=True)

    def verify_independently(self, args: AppFocusIn) -> IndependentToolVerification:
        front = self._ac.frontmost()
        focused = front is not None and (front.name == args.app or front.bundle_id == args.app)
        return IndependentToolVerification(
            passed=focused,
            detail=(
                f"application {args.app!r} is frontmost"
                if focused
                else f"application {args.app!r} is not frontmost"
            ),
        )


async def _wait_for_running(control: AppControl, target: str, timeout_s: float = 2.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        if any(app.name == target or app.bundle_id == target for app in control.list_running()):
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(0.05)


async def _wait_for_frontmost(control: AppControl, target: str, timeout_s: float = 5.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    next_activation = loop.time()
    while True:
        front = control.frontmost()
        if front is not None and (front.name == target or front.bundle_id == target):
            return True
        now = loop.time()
        if now >= deadline:
            return False
        if now >= next_activation:
            control.activate(target)
            next_activation = now + 0.25
        await asyncio.sleep(0.05)


def register_app_tools(registry: ToolRegistry, adapter: AppControl | None = None) -> None:
    ac = adapter or default_app_control()
    for tool in (AppList(ac), AppLaunch(ac), AppFocus(ac)):
        registry.register(tool)
