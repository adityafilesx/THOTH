from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from thoth_daemon.events.bus import EventBus

router = APIRouter()


@router.websocket("/ws")
async def event_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    bus: EventBus = websocket.app.state.bus
    queue = bus.subscribe()
    try:
        await websocket.send_json({"type": "connection.established", "payload": {}})
        while True:
            envelope = await queue.get()
            await websocket.send_json(envelope)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
