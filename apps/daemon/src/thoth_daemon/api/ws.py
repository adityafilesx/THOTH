import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from thoth_daemon.events.bus import EventBus
from thoth_daemon.security.auth import token_matches

router = APIRouter()

_AUTH_TIMEOUT_S = 5.0


@router.websocket("/ws")
async def event_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    expected = getattr(websocket.app.state, "session_token", None)
    # Browsers cannot set headers on a WebSocket, so authenticate via a
    # first-message handshake before streaming anything.
    try:
        frame = await asyncio.wait_for(websocket.receive_json(), timeout=_AUTH_TIMEOUT_S)
    except (TimeoutError, WebSocketDisconnect, ValueError):
        await websocket.close(code=1008)
        return
    provided = frame.get("token") if isinstance(frame, dict) else None
    if not token_matches(provided, expected):
        await websocket.close(code=1008)
        return

    bus: EventBus = websocket.app.state.bus
    queue = bus.subscribe()
    try:
        await websocket.send_json({"type": "connection.established", "payload": {}})
        while True:
            event_ready = asyncio.create_task(queue.get())
            client_ready = asyncio.create_task(websocket.receive())
            done, pending = await asyncio.wait(
                {event_ready, client_ready},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for waiter in pending:
                waiter.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

            if client_ready in done:
                frame = client_ready.result()
                if frame.get("type") == "websocket.disconnect":
                    break
            if event_ready in done:
                await websocket.send_json(event_ready.result())
    except (asyncio.CancelledError, RuntimeError, WebSocketDisconnect):
        pass
    finally:
        bus.unsubscribe(queue)
