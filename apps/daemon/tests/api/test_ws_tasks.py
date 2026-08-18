from fastapi.testclient import TestClient


def _drain(ws, limit: int = 80) -> list[dict]:
    events: list[dict] = []
    for _ in range(limit):
        msg = ws.receive_json()
        events.append(msg)
        if msg["type"] == "approval.requested":
            break
        payload = msg.get("payload", {})
        task = payload.get("task")
        if msg["type"] == "task.state_changed" and task and task["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
    return events


def test_ws_streams_ordered_task_events(ws_client: TestClient) -> None:
    with ws_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "test-token"})
        assert ws.receive_json()["type"] == "connection.established"
        resp = ws_client.post("/api/tasks", json={"goal": "read my notes"})
        assert resp.json()["state"] == "COMPLETED"

        events = _drain(ws)
        types = [e["type"] for e in events]
        assert "task.created" in types
        assert "task.state_changed" in types
        assert "audit.appended" in types

        # State transitions arrive in lifecycle order.
        states = [e["payload"]["task"]["state"] for e in events if e["type"] == "task.state_changed"]
        for expected in ["UNDERSTANDING", "PLANNING", "RISK_REVIEW", "EXECUTING"]:
            assert expected in states
        assert states.index("PLANNING") < states.index("EXECUTING")


def test_ws_emits_approval_request_event(ws_client: TestClient) -> None:
    with ws_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "test-token"})
        ws.receive_json()  # hello
        ws_client.post("/api/tasks", json={"goal": "send the email"})
        events = _drain(ws)
        assert any(e["type"] == "approval.requested" for e in events)
