from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from thoth_daemon.api import health, permissions, tasks, ws
from thoth_daemon.api.middleware import BearerAuthMiddleware
from thoth_daemon.audit.store import AuditStore
from thoth_daemon.config import Settings
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.planner import DeterministicMockPlanner
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.scope import ScopeEnforcer
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.events.bus import EventBus
from thoth_daemon.logging_setup import configure_logging, get_logger
from thoth_daemon.schemas import ResourceScope, WorkspaceProfile
from thoth_daemon.security.auth import mint_token, write_token_file
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.storage.permissions import PermissionStore
from thoth_daemon.tools.fs_tools import register_fs_tools
from thoth_daemon.tools.mock_tools import build_registry
from thoth_daemon.tools.shell_tool import register_shell_tool


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(cfg.log_dir, cfg.log_level)
        log = get_logger("thoth.app")
        engine = make_engine(cfg.db_path)
        await init_schema(engine)
        session_factory = make_session_factory(engine)
        bus = EventBus()
        app.state.settings = cfg
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.bus = bus

        # Per-session auth token: env-provided (dev/tests) or minted, then
        # written 0600 for the desktop to read (threat T6).
        token = cfg.session_token or mint_token()
        app.state.session_token = token
        write_token_file(cfg.session_token_path, token)

        async def publish(event_type: str, payload: dict[str, Any]) -> None:
            await bus.publish(event_type, payload)

        permissions_store = PermissionStore(session_factory)
        existing = await permissions_store.list_workspaces()
        if existing:
            default_ws = existing[0]
        else:
            default_ws = WorkspaceProfile(
                name="default",
                root_path=cfg.trusted_workspaces[0] if cfg.trusted_workspaces else "",
                trusted=bool(cfg.trusted_workspaces),
            )
            await permissions_store.upsert_workspace(default_ws)
        app.state.permissions = permissions_store

        audit_store = AuditStore(session_factory)
        app.state.audit = audit_store

        async def scope_provider() -> ResourceScope:
            return await permissions_store.effective_scope(default_ws.id)

        registry = build_registry()
        register_fs_tools(registry)  # real, scoped filesystem tools (slice 3)
        register_shell_tool(registry)  # restricted shell (slice 4)
        app.state.orchestrator = Orchestrator(
            registry=registry,
            policy=PolicyEngine(),
            approvals=ApprovalEngine(ttl_seconds=cfg.approval_ttl_seconds),
            verifier=VerificationEngine(),
            recovery=RecoveryController(
                max_retries_per_step=cfg.max_retries_per_step,
                max_retries_per_task=cfg.max_retries_per_task,
            ),
            audit=audit_store,
            planner=DeterministicMockPlanner(),
            publish=publish,
            workspace=default_ws,
            enforcer=ScopeEnforcer(),
            scope_provider=scope_provider,
        )
        log.info("daemon_started", extra={"data": {"host": cfg.host, "port": cfg.port}})
        yield
        log.info("daemon_stopped")
        await engine.dispose()

    app = FastAPI(title="THOTH Daemon", lifespan=lifespan)
    app.add_middleware(BearerAuthMiddleware)
    app.include_router(health.router)
    app.include_router(tasks.router)
    app.include_router(ws.router)
    app.include_router(permissions.router)
    return app
