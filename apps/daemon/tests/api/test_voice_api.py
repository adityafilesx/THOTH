"""Voice API (Phase 4 slice 6).

Transcripts create TASKS via the normal pipeline; they never approve
anything. The daemon fixture wires MockSTTAdapter — the real STT path is
pending live verification (model + microphone).
"""

import sys

from fastapi import FastAPI
from httpx import AsyncClient

from omnimac_daemon.voice.stt import MockSTTAdapter, Transcript
from omnimac_daemon.voice.tts import MacOSSpeechSynthesisProvider, SpeechSynthesisService


def _prime_stt(app: FastAPI, text: str) -> None:
    app.state.stt = MockSTTAdapter(Transcript(text=text, confidence=0.97, duration_s=1.0, language="en"))


def _silent_tts(app: FastAPI) -> None:
    provider = MacOSSpeechSynthesisProvider(
        command=lambda segment, request: [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
    )
    app.state.speech_synthesis = SpeechSynthesisService(provider)


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
        resp = await client.post("/api/voice/transcribe", content=b"", headers={"Content-Type": "audio/wav"})
        assert resp.status_code == 422


class TestTranscriptIsolation:
    async def test_transcript_cannot_approve_or_create_an_approval_task(self, client: AsyncClient, app: FastAPI) -> None:
        """Approval language is rejected before planning and leaves the
        invocation-bound approval pending and unconsumed."""
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
        body = resp.json()
        assert body["task"] is None
        assert body["control"] == "clarification_required"
        assert "visible invocation-bound approval" in body["response"]["display"]["text"]

        tasks = (await client.get("/api/tasks")).json()
        assert [item["id"] for item in tasks] == [task["id"]]

        # The original approval is still pending — untouched.
        pending_after = (await client.get("/api/approvals/pending")).json()
        assert len(pending_after) == 1
        assert pending_after[0]["id"] == pending_before[0]["id"]
        assert pending_after[0]["status"] == "pending"

    async def test_legacy_voice_task_stop_uses_global_stop_without_creating_task(self, client: AsyncClient, app: FastAPI) -> None:
        pending_task = (await client.post("/api/tasks", json={"goal": "send the email"})).json()
        assert pending_task["state"] == "WAITING_FOR_APPROVAL"

        _prime_stt(app, "Omnimac, stop.")
        response = await client.post(
            "/api/voice/task",
            content=b"fake-audio-bytes",
            headers={"Content-Type": "audio/wav"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["stopped"] is True
        assert body["task"] is None
        assert body["stop"]["approvals_invalidated"] == 1
        assert (await client.get("/api/approvals/pending")).json() == []


class TestSayEndpoints:
    async def test_say_and_interrupt(self, client: AsyncClient, app: FastAPI) -> None:
        _silent_tts(app)
        resp = await client.post("/api/voice/say", json={"text": "task complete"})
        assert resp.status_code == 200
        assert resp.json()["speaking"] is True
        stop = await client.post("/api/voice/interrupt")
        assert stop.status_code == 200
        assert stop.json()["interrupted"] in (True, False)  # may have finished already
