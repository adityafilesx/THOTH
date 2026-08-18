import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from omnimac_daemon.api.ws import event_stream
from omnimac_daemon.events.bus import EventBus


def test_ws_receives_published_events(ws_client: TestClient, app: FastAPI) -> None:
    bus: EventBus = app.state.bus
    with ws_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "test-token"})
        hello = ws.receive_json()
        assert hello["type"] == "connection.established"

        ws_client.portal.call(bus.publish, "task.state_changed", {"task_id": "t1", "to": "PLANNING"})
        msg = ws.receive_json()
        assert msg["type"] == "task.state_changed"
        assert msg["payload"] == {"task_id": "t1", "to": "PLANNING"}
        assert "ts" in msg


def test_ws_events_are_redacted(ws_client: TestClient, app: FastAPI) -> None:
    bus: EventBus = app.state.bus
    with ws_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "test-token"})
        ws.receive_json()  # hello
        ws_client.portal.call(bus.publish, "audit.appended", {"api_key": "sk-super-secret", "detail": "fine"})
        msg = ws.receive_json()
        assert msg["payload"]["api_key"] == "[REDACTED]"
        assert msg["payload"]["detail"] == "fine"


def test_ws_multiple_subscribers_each_get_events(ws_client: TestClient, app: FastAPI) -> None:
    bus: EventBus = app.state.bus
    with ws_client.websocket_connect("/ws") as a, ws_client.websocket_connect("/ws") as b:
        a.send_json({"type": "auth", "token": "test-token"})
        b.send_json({"type": "auth", "token": "test-token"})
        a.receive_json()
        b.receive_json()
        ws_client.portal.call(bus.publish, "task.created", {"task_id": "t2"})
        assert a.receive_json()["payload"]["task_id"] == "t2"
        assert b.receive_json()["payload"]["task_id"] == "t2"


def test_ws_rejects_wrong_token(ws_client: TestClient) -> None:
    with ws_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "wrong"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_ws_rejects_missing_auth_frame(ws_client: TestClient) -> None:
    with ws_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "not-auth"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


class _FakeBus:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.unsubscribed = False

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        return self.queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        assert queue is self.queue
        self.unsubscribed = True


class _FakeWebSocket:
    def __init__(self, bus: _FakeBus) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(session_token="test-token", bus=bus))
        self.hello_sent = asyncio.Event()
        self.disconnected = asyncio.Event()

    async def accept(self) -> None:
        return None

    async def receive_json(self) -> dict[str, str]:
        return {"type": "auth", "token": "test-token"}

    async def send_json(self, payload: dict[str, Any]) -> None:
        if payload["type"] == "connection.established":
            self.hello_sent.set()

    async def receive(self) -> dict[str, Any]:
        await self.disconnected.wait()
        return {"type": "websocket.disconnect", "code": 1000}


async def test_ws_shutdown_cancellation_is_clean() -> None:
    bus = _FakeBus()
    websocket = _FakeWebSocket(bus)
    task = asyncio.create_task(event_stream(websocket))  # type: ignore[arg-type]
    await websocket.hello_sent.wait()

    task.cancel()
    await task

    assert bus.unsubscribed is True


async def test_ws_client_disconnect_unsubscribes_without_waiting_for_an_event() -> None:
    bus = _FakeBus()
    websocket = _FakeWebSocket(bus)
    task = asyncio.create_task(event_stream(websocket))  # type: ignore[arg-type]
    await websocket.hello_sent.wait()

    websocket.disconnected.set()
    await task

    assert bus.unsubscribed is True
