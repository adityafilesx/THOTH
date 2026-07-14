from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import AsyncClient

from thoth_daemon.voice.contracts import FinalTranscript, TranscriptSegment
from thoth_daemon.voice.service import VoiceCommandService, VoiceSessionRegistry
from thoth_daemon.voice.stop import GlobalStopAuthority
from thoth_daemon.voice.stt import MockSpeechRecognitionProvider

NOW = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)


def _final(text: str) -> FinalTranscript:
    return FinalTranscript(
        text=text,
        confidence=0.95,
        language="en",
        duration_s=1,
        segments=(
            TranscriptSegment(
                text=text,
                start_s=0,
                end_s=1,
                confidence=0.95,
                final=True,
            ),
        ),
        completed_at=NOW,
    )


def _prime(app: FastAPI, text: str, *, retain_transcripts: bool = False) -> None:
    provider = MockSpeechRecognitionProvider(_final(text))
    sessions = VoiceSessionRegistry(
        provider,
        retain_transcripts=retain_transcripts,
        clock=lambda: NOW,
    )
    stop = GlobalStopAuthority(
        sessions=sessions,
        tts=app.state.speech_synthesis,
        orchestrator=app.state.orchestrator,
    )
    app.state.voice_sessions = sessions
    app.state.global_stop = stop
    app.state.voice_commands = VoiceCommandService(
        sessions=sessions,
        stop=stop,
        orchestrator=app.state.orchestrator,
        tts=app.state.speech_synthesis,
    )


async def _start(client: AsyncClient) -> str:
    response = await client.post("/api/voice/sessions", json={"mode": "hold"})
    assert response.status_code == 201
    body = response.json()
    assert body["activity"] == "listening"
    assert body["microphone_visible"] is True
    assert body["local_processing"] is True
    return str(body["session_id"])


class TestVoiceSessionLifecycle:
    async def test_partial_final_edit_and_exactly_once_task_submission(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        _prime(app, "run the tests")
        session_id = await _start(client)

        audio = await client.put(
            f"/api/voice/sessions/{session_id}/audio",
            content=b"local audio bytes",
            headers={"Content-Type": "audio/wav"},
        )
        assert audio.status_code == 200
        partial = await client.post(f"/api/voice/sessions/{session_id}/partial")
        assert partial.status_code == 200
        assert partial.json()["partial"]["text"] == "run the tests"

        final = await client.post(f"/api/voice/sessions/{session_id}/finalise")
        assert final.status_code == 200
        assert final.json()["final"]["text"] == "run the tests"
        assert final.json()["microphone_visible"] is False

        edited = await client.patch(
            f"/api/voice/sessions/{session_id}/transcript",
            json={"text": "run all tests"},
        )
        assert edited.status_code == 200
        assert edited.json()["editable_text"] == "run all tests"

        submitted = await client.post(f"/api/voice/sessions/{session_id}/submit")
        assert submitted.status_code == 200
        body = submitted.json()
        assert body["stopped"] is False
        assert body["task"]["source"] == "voice"
        assert body["task"]["goal"] == "run all tests"

        # Default privacy policy removes the transcript session after submit.
        missing = await client.get(f"/api/voice/sessions/{session_id}")
        assert missing.status_code == 404
        duplicate = await client.post(f"/api/voice/sessions/{session_id}/submit")
        assert duplicate.status_code == 404

    async def test_cancel_deletes_audio_and_hides_microphone(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        _prime(app, "ignored")
        session_id = await _start(client)
        await client.put(
            f"/api/voice/sessions/{session_id}/audio",
            content=b"private",
            headers={"Content-Type": "audio/wav"},
        )
        cancelled = await client.delete(f"/api/voice/sessions/{session_id}")
        assert cancelled.status_code == 200
        assert cancelled.json()["activity"] == "cancelled"
        assert cancelled.json()["microphone_visible"] is False

    async def test_retention_setting_keeps_only_transcript_state(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        _prime(app, "what am I working on", retain_transcripts=True)
        session_id = await _start(client)
        await client.put(
            f"/api/voice/sessions/{session_id}/audio",
            content=b"audio",
            headers={"Content-Type": "audio/wav"},
        )
        await client.post(f"/api/voice/sessions/{session_id}/finalise")
        await client.post(f"/api/voice/sessions/{session_id}/submit")
        retained = await client.get(f"/api/voice/sessions/{session_id}")
        assert retained.status_code == 200
        assert retained.json()["final"]["text"] == "what am I working on"
        assert "audio" not in retained.json()


class TestVoiceStopBypass:
    async def test_exact_stop_phrase_bypasses_task_creation_and_invalidates_approval(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        pending_task = (await client.post("/api/tasks", json={"goal": "send the email"})).json()
        assert pending_task["state"] == "WAITING_FOR_APPROVAL"
        assert len((await client.get("/api/approvals/pending")).json()) == 1

        _prime(app, "Thoth, stop.")
        session_id = await _start(client)
        await client.put(
            f"/api/voice/sessions/{session_id}/audio",
            content=b"spoken stop",
            headers={"Content-Type": "audio/wav"},
        )
        await client.post(f"/api/voice/sessions/{session_id}/finalise")
        stopped = await client.post(f"/api/voice/sessions/{session_id}/submit")

        assert stopped.status_code == 200
        body = stopped.json()
        assert body["stopped"] is True
        assert body["task"] is None
        assert body["stop"]["approvals_invalidated"] == 1
        assert (await client.get("/api/approvals/pending")).json() == []

    async def test_visible_global_stop_endpoint_is_model_free(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        _prime(app, "unused")
        response = await client.post("/api/stop", json={"reason": "global_button"})
        assert response.status_code == 200
        assert response.json()["reason"] == "global_button"
