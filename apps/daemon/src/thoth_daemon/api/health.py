from fastapi import APIRouter, Request
from sqlalchemy import text

import thoth_daemon

router = APIRouter()


@router.get("/api/health")
async def health(request: Request) -> dict[str, str]:
    db_status = "error"
    try:
        session_factory = request.app.state.session_factory
        async with session_factory() as session:
            await session.execute(text("SELECT 1 FROM tasks LIMIT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001 - health must not raise
        db_status = "error"
    return {"status": "ok", "version": thoth_daemon.__version__, "db": db_status}
