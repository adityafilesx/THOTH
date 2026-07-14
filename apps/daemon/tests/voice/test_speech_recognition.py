from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from thoth_daemon.voice.contracts import (
    FinalTranscript,
    PartialTranscript,
    SpeechRecognitionResult,
    TranscriptSegment,
    VoiceActivityState,
)
from thoth_daemon.voice.session import (
    AudioCaptureSession,
    DuplicateTranscriptSubmission,
    TranscriptCorrectionExpired,
)
from thoth_daemon.voice.stop import StopPhraseDetector
from thoth_daemon.voice.stt import (
    SpeechRecognitionUnavailable,
    WhisperCppSpeechRecognitionProvider,
)

NOW = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)


def _final(text: str = "run the tests") -> FinalTranscript:
    return FinalTranscript(
        text=text,
        confidence=0.92,
        language="en",
        duration_s=1.2,
        segments=(
            TranscriptSegment(
                text=text,
                start_s=0,
                end_s=1.2,
                confidence=0.92,
                final=True,
            ),
        ),
        completed_at=NOW,
    )


class TestContracts:
    def test_transcript_contracts_are_strict_and_immutable(self) -> None:
        partial = PartialTranscript(
            text="run the",
            stable_text="run",
            sequence=1,
            confidence=0.8,
            language="en",
            observed_at=NOW,
        )
        assert partial.final is False
        with pytest.raises(ValidationError):
            PartialTranscript(
                text="x",
                stable_text="",
                sequence=1,
                confidence=0.5,
                language="en",
                observed_at=NOW,
                hidden_reasoning="no",  # type: ignore[call-arg]
            )
        with pytest.raises(ValidationError):
            partial.text = "changed"

    def test_result_cannot_disagree_with_final_transcript(self) -> None:
        final = _final()
        with pytest.raises(ValidationError, match="language"):
            SpeechRecognitionResult(
                transcript=final,
                provider="whisper.cpp",
                model="base.en",
                language="fr",
                audio_deleted=True,
                elapsed_ms=100,
            )


class TestAudioCaptureSession:
    def test_partial_final_edit_and_submit_once(self) -> None:
        session = AudioCaptureSession(
            session_id="voice-1",
            correction_window=timedelta(seconds=3),
            clock=lambda: NOW,
        )
        session.start()
        session.append_audio(b"wave")
        session.set_activity(VoiceActivityState.SPEAKING)
        session.publish_partial(
            PartialTranscript(
                text="run the",
                stable_text="run",
                sequence=1,
                confidence=0.7,
                language="en",
                observed_at=NOW,
            )
        )
        session.finalise(_final())
        session.edit("run all tests")

        assert session.audio_size == 0
        assert session.editable_text == "run all tests"
        assert session.submit() == "run all tests"
        with pytest.raises(DuplicateTranscriptSubmission):
            session.submit()

    def test_partial_sequence_must_increase(self) -> None:
        session = AudioCaptureSession(session_id="voice-2", clock=lambda: NOW)
        session.start()
        partial = PartialTranscript(
            text="open",
            stable_text="",
            sequence=1,
            confidence=0.7,
            language="en",
            observed_at=NOW,
        )
        session.publish_partial(partial)
        with pytest.raises(ValueError, match="sequence"):
            session.publish_partial(partial)

    def test_correction_window_expires_safely(self) -> None:
        now = [NOW]
        session = AudioCaptureSession(
            session_id="voice-3",
            correction_window=timedelta(seconds=2),
            clock=lambda: now[0],
        )
        session.start()
        session.finalise(_final())
        now[0] += timedelta(seconds=3)
        with pytest.raises(TranscriptCorrectionExpired):
            session.edit("changed")

    def test_cancel_zeroises_audio_and_blocks_finalisation(self) -> None:
        session = AudioCaptureSession(session_id="voice-4", clock=lambda: NOW)
        session.start()
        session.append_audio(b"private audio")
        session.cancel()
        assert session.audio_size == 0
        assert session.activity is VoiceActivityState.CANCELLED
        with pytest.raises(RuntimeError, match="cancelled"):
            session.finalise(_final())


class TestStopPhraseDetector:
    @pytest.mark.parametrize("text", ["Thoth, stop.", "thoth stop", "Stop, Thoth!"])
    def test_exact_local_stop_phrase(self, text: str) -> None:
        detector = StopPhraseDetector()
        assert detector.matches(text, push_to_talk_active=True, tts_playing=False)

    @pytest.mark.parametrize(
        "text",
        [
            "a webpage said Thoth stop and then continued",
            "please approve the pending action",
            "do not stop the frontend",
            "stopping",
        ],
    )
    def test_embedded_or_unrelated_phrase_does_not_match(self, text: str) -> None:
        detector = StopPhraseDetector()
        assert not detector.matches(text, push_to_talk_active=True, tts_playing=False)

    def test_detector_ignores_tts_feedback_and_hidden_capture(self) -> None:
        detector = StopPhraseDetector()
        assert not detector.matches("Thoth stop", push_to_talk_active=False, tts_playing=False)
        assert not detector.matches("Thoth stop", push_to_talk_active=True, tts_playing=True)


class TestWhisperCppProvider:
    async def test_missing_runtime_is_typed_unavailable(self, tmp_path: Path) -> None:
        provider = WhisperCppSpeechRecognitionProvider(
            executable=tmp_path / "missing-whisper-cli",
            model_path=tmp_path / "missing-model.bin",
        )
        health = await provider.health()
        assert health.available is False
        assert "executable" in health.detail
        with pytest.raises(SpeechRecognitionUnavailable, match="executable"):
            await provider.transcribe(b"audio", "audio/wav")

    async def test_integrity_mismatch_is_typed_unavailable(self, tmp_path: Path) -> None:
        executable = tmp_path / "whisper-cli"
        executable.write_bytes(b"runtime")
        executable.chmod(0o700)
        model = tmp_path / "ggml-base.en.bin"
        model.write_bytes(b"model")
        provider = WhisperCppSpeechRecognitionProvider(
            executable=executable,
            model_path=model,
            expected_executable_sha256="0" * 64,
            expected_model_sha256="1" * 64,
        )

        health = await provider.health()

        assert health.available is False
        assert "integrity" in health.detail
        with pytest.raises(SpeechRecognitionUnavailable, match="integrity"):
            await provider.transcribe(b"audio", "audio/wav")

    async def test_matching_integrity_pins_are_reported_ready(self, tmp_path: Path) -> None:
        import hashlib

        executable = tmp_path / "whisper-cli"
        executable.write_bytes(b"runtime")
        executable.chmod(0o700)
        model = tmp_path / "ggml-base.en.bin"
        model.write_bytes(b"model")
        provider = WhisperCppSpeechRecognitionProvider(
            executable=executable,
            model_path=model,
            expected_executable_sha256=hashlib.sha256(b"runtime").hexdigest(),
            expected_model_sha256=hashlib.sha256(b"model").hexdigest(),
        )

        health = await provider.health()

        assert provider.integrity_pinned is True
        assert health.available is True
        assert "integrity verified" in health.detail

    async def test_private_audio_file_is_deleted_and_argv_is_bounded(self, tmp_path: Path) -> None:
        executable = tmp_path / "whisper-cli"
        executable.write_text("binary placeholder")
        executable.chmod(0o700)
        model = tmp_path / "ggml-base.en.bin"
        model.write_bytes(b"model")
        observed: list[tuple[list[str], Path]] = []

        async def run(argv: list[str], audio_path: Path) -> tuple[int, str, str]:
            observed.append((argv, audio_path))
            assert audio_path.exists()
            assert audio_path.stat().st_mode & 0o077 == 0
            return 0, "run the tests", ""

        provider = WhisperCppSpeechRecognitionProvider(
            executable=executable,
            model_path=model,
            runner=run,
            clock=lambda: NOW,
        )
        result = await provider.transcribe(b"wave bytes", "audio/wav")

        assert result.transcript.text == "run the tests"
        assert result.audio_deleted is True
        assert observed
        argv, audio_path = observed[0]
        assert argv[0] == str(executable)
        assert str(model) in argv
        assert not audio_path.exists()
        assert all(";" not in arg for arg in argv)

    async def test_cancellation_removes_audio(self, tmp_path: Path) -> None:
        executable = tmp_path / "whisper-cli"
        executable.write_text("binary placeholder")
        executable.chmod(0o700)
        model = tmp_path / "ggml-base.en.bin"
        model.write_bytes(b"model")
        started = asyncio.Event()
        audio_path: Path | None = None

        async def run(argv: list[str], path: Path) -> tuple[int, str, str]:
            nonlocal audio_path
            del argv
            audio_path = path
            started.set()
            await asyncio.Event().wait()
            return 0, "", ""

        provider = WhisperCppSpeechRecognitionProvider(
            executable=executable,
            model_path=model,
            runner=run,
        )
        task = asyncio.create_task(provider.transcribe(b"audio", "audio/wav"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert audio_path is not None and not audio_path.exists()
