"""HTTP auth middleware — every request needs the session bearer token
except the liveness probe.

Implemented as a pure ASGI middleware (not Starlette's BaseHTTPMiddleware,
which does not pass WebSocket connections through cleanly and can hang them).
Only ``http`` scopes are guarded; ``websocket`` and ``lifespan`` pass straight
through — WebSocket auth is a first-message handshake in api/ws.py."""

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from thoth_daemon.security.auth import token_matches

_OPEN_PATHS = frozenset({"/api/health"})


class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        if request.url.path in _OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        expected = getattr(request.app.state, "session_token", None)
        header = request.headers.get("Authorization", "")
        provided = header[7:] if header.startswith("Bearer ") else None
        if not token_matches(provided, expected):
            await JSONResponse({"detail": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)
