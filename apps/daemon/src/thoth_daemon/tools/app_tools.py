"""macOS app-control tools (Phase 3 slice 6). Launch, focus, and list running
apps via an injected AppControl adapter (real NSWorkspace by default). Launch
and focus declare requested_scope(apps=[name]) so the slice-1 enforcer refuses
any app not in the workspace's approved_apps. No AX element interaction (TCC)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.macos.app_control import AppControl, default_app_control
from thoth_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from thoth_daemon.tools.base import ToolDefinition
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
        if not ok or not any(a.name == args.app for a in self._ac.list_running()):
            raise RuntimeError(f"failed to launch {args.app}")
        return AppLaunchOut(app=args.app, launched=True)


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
        front = self._ac.frontmost()
        if not ok or front is None or front.name != args.app:
            raise RuntimeError(f"failed to focus {args.app}")
        return AppFocusOut(app=args.app, focused=True)


def register_app_tools(registry: ToolRegistry, adapter: AppControl | None = None) -> None:
    ac = adapter or default_app_control()
    for tool in (AppList(ac), AppLaunch(ac), AppFocus(ac)):
        registry.register(tool)
