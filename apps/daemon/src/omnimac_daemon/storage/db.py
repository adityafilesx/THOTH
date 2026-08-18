from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from omnimac_daemon.storage.models import Base


def make_engine(db_path: Path) -> AsyncEngine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(f"sqlite+aiosqlite:///{db_path}")


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_schema(engine: AsyncEngine) -> None:
    """Idempotent schema creation for dev/tests.

    Production evolution goes through Alembic (`make migrate`); migration
    0001 mirrors these models exactly.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
