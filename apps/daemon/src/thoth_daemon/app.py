from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from thoth_daemon.api import health, tasks, ws
from thoth_daemon.audit.store import AuditStore
from thoth_daemon.config import Settings
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.planner import DeterministicMockPlanner
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.events.bus import EventBus
from thoth_daemon.logging_setup import configure_logging, get_logger
from thoth_daemon.schemas import WorkspaceProfile
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.tools.mock_tools import build_registry


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

        async def publish(event_type: str, payload: dict[str, Any]) -> None:
            await bus.publish(event_type, payload)

        workspace = WorkspaceProfile(
            name="default",
            root_path=cfg.trusted_workspaces[0] if cfg.trusted_workspaces else "",
            trusted=bool(cfg.trusted_workspaces),
        )
        app.state.orchestrator = Orchestrator(
            registry=build_registry(),
            policy=PolicyEngine(),
            approvals=ApprovalEngine(ttl_seconds=cfg.approval_ttl_seconds),
            verifier=VerificationEngine(),
            recovery=RecoveryController(
                max_retries_per_step=cfg.max_retries_per_step,
                max_retries_per_task=cfg.max_retries_per_task,
            ),
            audit=AuditStore(session_factory),
            planner=DeterministicMockPlanner(),
            publish=publish,
            workspace=workspace,
        )
        log.info("daemon_started", extra={"data": {"host": cfg.host, "port": cfg.port}})
        yield
        log.info("daemon_stopped")
        await engine.dispose()

    app = FastAPI(title="THOTH Daemon", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(tasks.router)
    app.include_router(ws.router)
    return app
