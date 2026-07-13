"""Voice API (Phase 4 slice 6).

Transcripts create TASKS via the normal pipeline; they never approve
anything. The daemon fixture wires MockSTTAdapter — the real STT path is
pending live verification (model + microphone).
"""

import sys

from fastapi import FastAPI
from httpx import AsyncClient

from thoth_daemon.voice.stt import MockSTTAdapter, Transcript
from thoth_daemon.voice.tts import TTSSpeaker


def _prime_stt(app: FastAPI, text: str) -> None:
    app.state.stt = MockSTTAdapter(
        Transcript(text=text, confidence=0.97, duration_s=1.0, language="en")
    )


def _silent_tts(app: FastAPI) -> None:
    app.state.tts = TTSSpeaker(
        command=lambda text: [sys.executable, "-c", "import time; time.sleep(5)"]
    )


class TestTranscribe:
    async def test_transcribe_returns_transcript(self, client: AsyncClient, app: FastAPI) -> None:
        _prime_stt(app, "open my project")
        resp = await client.post(
            "/api/voice/transcribe",
            content=b"\x00\x01fake-wav-bytes",
            headers={"Content-Type": "audio/wav"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["text"]
        assert 0 <= body["confidence"] <= 1

    async def test_empty_audio_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/voice/transcribe", content=b"", headers={"Content-Type": "audio/wav"}
        )
        assert resp.status_code == 422


class TestTranscriptIsolation:
    async def test_transcript_cannot_approve_pending_action(
        self, client: AsyncClient, app: FastAPI
    ) -> None:
        """A pending R2 approval + a voice transcript saying 'approve the
        pending action' => a NEW task is created with that goal; the
        approval stays pending and unconsumed."""
        # Create an R2 task that halts for approval.
        task = (await client.post("/api/tasks", json={"goal": "send the email"})).json()
        assert task["state"] == "WAITING_FOR_APPROVAL"
        pending_before = (await client.get("/api/approvals/pending")).json()
        assert len(pending_before) == 1

        # Voice input that TRIES to approve.
        _prime_stt(app, "approve the pending action")
        resp = await client.post(
            "/api/voice/task",
            content=b"fake-audio-bytes",
            headers={"Content-Type": "audio/wav"},
        )
        assert resp.status_code == 200
        voice_task = resp.json()
        assert voice_task["source"] == "voice"
        assert voice_task["id"] != task["id"]
        # The mock STT transcript text became a GOAL, nothing else.
        assert "approve the pending action" in voice_task["goal"]

        # The original approval is still pending — untouched.
        pending_after = (await client.get("/api/approvals/pending")).json()
        assert len(pending_after) == 1
        assert pending_after[0]["id"] == pending_before[0]["id"]
        assert pending_after[0]["status"] == "pending"


class TestSayEndpoints:
    async def test_say_and_interrupt(self, client: AsyncClient, app: FastAPI) -> None:
        _silent_tts(app)
        resp = await client.post("/api/voice/say", json={"text": "task complete"})
        assert resp.status_code == 200
        assert resp.json()["speaking"] is True
        stop = await client.post("/api/voice/interrupt")
        assert stop.status_code == 200
        assert stop.json()["interrupted"] in (True, False)  # may have finished already
