"""Voice input/output (Phase 4 slice 6).

STT runs behind an adapter — MockSTTAdapter here; the faster-whisper
implementation needs a model + microphone and is pending live
verification. TTS uses real /usr/bin/say, tested hermetically with an
injected command and live (file output, silent) where `say` exists.

A voice transcript is USER-ADJACENT input that becomes a task GOAL via
the normal submit pipeline. It is NEVER an approval: a transcript saying
"approve the pending action" must not touch the ApprovalEngine.
"""

import asyncio
import shutil
import sys
import time
from pathlib import Path

import pytest

from omnimac_daemon.voice.stt import (
    MockSTTAdapter,
    SpeechRecognitionSTTAdapter,
    STTUnavailableError,
    Transcript,
    default_stt_adapter,
)
from omnimac_daemon.voice.tts import TTSSpeaker


class TestSTT:
    def test_default_adapter_is_local_whisper_not_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OmniMac_STT", raising=False)
        assert isinstance(default_stt_adapter(), SpeechRecognitionSTTAdapter)

    def test_mock_default_requires_explicit_test_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMNIMAC_STT", "mock")
        assert isinstance(default_stt_adapter(), MockSTTAdapter)

    async def test_mock_transcribe_round_trip(self) -> None:
        stt = MockSTTAdapter(Transcript(text="open my project", confidence=0.98, duration_s=1.2, language="en"))
        out = await stt.transcribe(b"\x00\x01fake-audio", "audio/wav")
        assert out.text == "open my project"
        assert stt.received and stt.received[0][1] == "audio/wav"

    async def test_unavailable_stt_raises_typed_error(self) -> None:
        from omnimac_daemon.voice.stt import FasterWhisperSTTAdapter

        stt = FasterWhisperSTTAdapter()
        try:
            import faster_whisper  # noqa: F401

            pytest.skip("faster-whisper installed; live path pending verification")
        except ImportError:
            pass
        with pytest.raises(STTUnavailableError, match="faster-whisper"):
            await stt.transcribe(b"x", "audio/wav")


def _slow_command(seconds: float) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


class TestTTS:
    async def test_speak_and_finish(self) -> None:
        speaker = TTSSpeaker(command=lambda text: _slow_command(0.1))
        handle = await speaker.speak("hello")
        await handle.wait()
        assert not speaker.is_speaking

    async def test_interrupt_terminates_quickly(self) -> None:
        speaker = TTSSpeaker(command=lambda text: _slow_command(30))
        await speaker.speak("long utterance")
        assert speaker.is_speaking
        start = time.monotonic()
        interrupted = await speaker.interrupt()
        elapsed = time.monotonic() - start
        assert interrupted
        assert elapsed < 0.5
        assert not speaker.is_speaking

    async def test_new_speak_interrupts_previous(self) -> None:
        speaker = TTSSpeaker(command=lambda text: _slow_command(30))
        first = await speaker.speak("first")
        second = await speaker.speak("second")
        # First utterance was interrupted by the second.
        await asyncio.wait_for(first.wait(), timeout=1.0)
        assert speaker.is_speaking  # second still going
        await speaker.interrupt()
        await asyncio.wait_for(second.wait(), timeout=1.0)

    async def test_interrupt_when_idle_returns_false(self) -> None:
        speaker = TTSSpeaker(command=lambda text: _slow_command(0.1))
        assert not await speaker.interrupt()


@pytest.mark.skipif(shutil.which("say") is None, reason="/usr/bin/say not available")
async def test_live_say_writes_audio_file(tmp_path: Path) -> None:
    """REAL /usr/bin/say, silent: render to an AIFF file and verify it."""
    out = tmp_path / "utterance.aiff"
    speaker = TTSSpeaker(command=lambda text: ["say", "-o", str(out), text])
    handle = await speaker.speak("omnimac")
    await asyncio.wait_for(handle.wait(), timeout=15.0)
    assert out.exists() and out.stat().st_size > 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
