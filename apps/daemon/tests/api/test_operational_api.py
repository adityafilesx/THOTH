"""Live Phase 5.2/5.3 daemon presentation and context surfaces."""

from httpx import AsyncClient


async def test_task_response_includes_authoritative_persona_and_stages(
    client: AsyncClient,
) -> None:
    task = (await client.post("/api/tasks", json={"goal": "read notes"})).json()
    assert task["state"] == "COMPLETED"
    assert task["presentation"]["authoritative"] is True
    assert task["presentation"]["response"]["intent"] == "verified_completion"
    assert task["presentation"]["stages"] == {
        "proposed": True,
        "approval": "not_required",
        "executed": True,
        "verified": True,
    }


async def test_pending_approval_response_is_deterministic(client: AsyncClient) -> None:
    task = (await client.post("/api/tasks", json={"goal": "send the email"})).json()
    presentation = task["presentation"]
    assert presentation["response"]["intent"] == "approval_required"
    assert presentation["response"]["used_model"] is False
    assert "Nothing has been sent" in presentation["display_response"]
    assert presentation["stages"]["approval"] == "pending"


async def test_denied_later_substep_produces_live_partial_completion(
    client: AsyncClient,
) -> None:
    await client.post("/api/tasks", json={"goal": "send the email"})
    pending = (await client.get("/api/approvals/pending")).json()
    response = await client.post(
        f"/api/approvals/{pending[0]['id']}/decision",
        json={"approved": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "FAILED"
    assert body["presentation"]["response"]["intent"] == "partial_completion"
    assert "Read the draft" in body["presentation"]["display_response"]
    assert "approval denied" in body["presentation"]["display_response"]


async def test_operational_status_exposes_live_context_fields(client: AsyncClient) -> None:
    task = (await client.post("/api/tasks", json={"goal": "read notes"})).json()
    response = await client.get(f"/api/operational-status/{task['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task["id"]
    assert body["runtime_status"] in {
        "unavailable",
        "starting",
        "ready",
        "generating",
        "degraded",
        "failed",
    }
    assert "foreground" in body
    assert "planned_focus_policy" in body
    assert "dialogue_expires_at" in body


async def test_foreground_capture_and_six_profiles_are_live(client: AsyncClient) -> None:
    foreground = await client.get("/api/foreground", params={"reason": "test"})
    assert foreground.status_code == 200
    assert foreground.json()["reason"] == "test"
    profiles = (await client.get("/api/application-profiles")).json()
    assert len(profiles) == 6
    assert any(profile["bundle_id"] == "com.apple.finder" for profile in profiles)


async def test_accessibility_status_is_live_bounded_and_requires_explicit_settings_request(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/accessibility")
    assert response.status_code == 200
    body = response.json()
    assert body["permission"]["status"] in {
        "not_determined",
        "denied",
        "granted",
        "revoked",
        "unavailable",
    }
    assert len(body["applications"]) == 6
    assert set(body["diagnostics"]) >= {
        "current_task_id",
        "semantic_target",
        "resolution_method",
        "resolution_confidence",
        "focus_policy",
        "verification_evidence",
        "permission_error",
        "clarification_required",
    }
    assert "windows" not in body["diagnostics"]
    assert "elements" not in body["diagnostics"]

    refused = await client.post(
        "/api/accessibility/open-settings",
        json={"user_requested": False},
    )
    assert refused.status_code == 422


async def test_dialogue_state_is_created_and_cannot_approve(client: AsyncClient) -> None:
    task = (await client.post("/api/tasks", json={"goal": "send the email"})).json()
    state = await client.get(f"/api/dialogue/{task['id']}")
    assert state.status_code == 200
    assert state.json()["pending_approval_id"]

    replay = await client.post(f"/api/dialogue/{task['id']}/resolve", json={"text": "approve it"})
    assert replay.status_code == 409
    pending = (await client.get("/api/approvals/pending")).json()
    assert len(pending) == 1


async def test_dialogue_dont_push_is_a_hard_live_constraint(client: AsyncClient) -> None:
    task = (await client.post("/api/tasks", json={"goal": "read notes"})).json()
    response = await client.post(
        f"/api/dialogue/{task['id']}/resolve", json={"text": "Don't push."}
    )
    assert response.status_code == 200
    assert "no_push" in response.json()["constraints"]
    state = (await client.get(f"/api/dialogue/{task['id']}")).json()
    assert "no_push" in state["constraints"]


async def test_persona_compose_endpoint_is_explicitly_non_authoritative(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/persona/compose",
        json={
            "fact": {
                "intent": "verified_completion",
                "verified": True,
                "succeeded_items": ["The requested check passed"],
            },
            "mode": "standard",
            "use_local_summary": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["authoritative"] is False
    assert response.json()["response"]["used_model"] is False
