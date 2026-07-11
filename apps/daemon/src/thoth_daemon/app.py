from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from thoth_daemon.api import health, ws
from thoth_daemon.config import Settings
from thoth_daemon.events.bus import EventBus
from thoth_daemon.logging_setup import configure_logging, get_logger
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(cfg.log_dir, cfg.log_level)
        log = get_logger("thoth.app")
        engine = make_engine(cfg.db_path)
        await init_schema(engine)
        app.state.settings = cfg
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        app.state.bus = EventBus()
        log.info("daemon_started", extra={"data": {"host": cfg.host, "port": cfg.port}})
        yield
        log.info("daemon_stopped")
        await engine.dispose()

    app = FastAPI(title="THOTH Daemon", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(ws.router)
    return app
