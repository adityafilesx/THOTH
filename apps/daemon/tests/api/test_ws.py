from fastapi import FastAPI
from fastapi.testclient import TestClient

from thoth_daemon.events.bus import EventBus


def test_ws_receives_published_events(ws_client: TestClient, app: FastAPI) -> None:
    bus: EventBus = app.state.bus
    with ws_client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "connection.established"

        ws_client.portal.call(
            bus.publish, "task.state_changed", {"task_id": "t1", "to": "PLANNING"}
        )
        msg = ws.receive_json()
        assert msg["type"] == "task.state_changed"
        assert msg["payload"] == {"task_id": "t1", "to": "PLANNING"}
        assert "ts" in msg


def test_ws_events_are_redacted(ws_client: TestClient, app: FastAPI) -> None:
    bus: EventBus = app.state.bus
    with ws_client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws_client.portal.call(
            bus.publish, "audit.appended", {"api_key": "sk-super-secret", "detail": "fine"}
        )
        msg = ws.receive_json()
        assert msg["payload"]["api_key"] == "[REDACTED]"
        assert msg["payload"]["detail"] == "fine"


def test_ws_multiple_subscribers_each_get_events(ws_client: TestClient, app: FastAPI) -> None:
    bus: EventBus = app.state.bus
    with ws_client.websocket_connect("/ws") as a, ws_client.websocket_connect("/ws") as b:
        a.receive_json()
        b.receive_json()
        ws_client.portal.call(bus.publish, "task.created", {"task_id": "t2"})
        assert a.receive_json()["payload"]["task_id"] == "t2"
        assert b.receive_json()["payload"]["task_id"] == "t2"
