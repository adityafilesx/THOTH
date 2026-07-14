from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from thoth_daemon.core.persona import SpokenResponse
from thoth_daemon.voice.contracts import (
    SpeechPlaybackState,
    SpeechRequest,
    SpeechSegment,
    SpeechVoice,
)
from thoth_daemon.voice.tts import (
    MacOSSpeechSynthesisProvider,
    PiperSpeechSynthesisProvider,
    SpeechSynthesisService,
    SpeechSynthesisUnavailable,
)


def _sleep_command(seconds: float) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


class TestSpeechContracts:
    def test_request_is_strict_bounded_and_immutable(self) -> None:
        request = SpeechRequest(
            segments=(SpeechSegment(text="Understood."),),
            voice=SpeechVoice(identifier="Samantha", display_name="Samantha", language="en-US"),
            rate_wpm=190,
        )
        assert request.segments[0].text == "Understood."
        with pytest.raises(ValidationError):
            request.rate_wpm = 500
        with pytest.raises(ValidationError):
            SpeechRequest(segments=())

    def test_segment_requires_text_or_local_cue(self) -> None:
        with pytest.raises(ValidationError, match="text or cue"):
            SpeechSegment()
        assert SpeechSegment(cue="confirmation").cue == "confirmation"


class TestMacOSProvider:
    async def test_segmented_local_playback_uses_voice_rate_and_no_shell(self) -> None:
        commands: list[list[str]] = []

        def command(segment: SpeechSegment, request: SpeechRequest) -> list[str]:
            commands.append(
                [
                    "say",
                    "-v",
                    request.voice.identifier if request.voice else "default",
                    "-r",
                    str(request.rate_wpm),
                    segment.text,
                ]
            )
            return _sleep_command(0.01)

        provider = MacOSSpeechSynthesisProvider(command=command)
        handle = await provider.speak(
            SpeechRequest(
                segments=(SpeechSegment(text="Checking."), SpeechSegment(text="Ready.")),
                voice=SpeechVoice(
                    identifier="Samantha",
                    display_name="Samantha",
                    language="en-US",
                ),
                rate_wpm=185,
            )
        )
        assert await handle.wait() == 0
        assert provider.state is SpeechPlaybackState.IDLE
        assert [command[-1] for command in commands] == ["Checking.", "Ready."]
        assert all("Samantha" in command and "185" in command for command in commands)

    async def test_interrupt_is_immediate(self) -> None:
        provider = MacOSSpeechSynthesisProvider(command=lambda segment, request: _sleep_command(30))
        await provider.speak(SpeechRequest(segments=(SpeechSegment(text="long"),)))
        await asyncio.sleep(0.02)
        start = time.monotonic()
        assert await provider.interrupt() is True
        assert time.monotonic() - start < 0.2
        assert provider.state is SpeechPlaybackState.INTERRUPTED

    async def test_local_confirmation_cue_is_supported(self) -> None:
        observed: list[SpeechSegment] = []

        def command(segment: SpeechSegment, request: SpeechRequest) -> list[str]:
            del request
            observed.append(segment)
            return _sleep_command(0.01)

        provider = MacOSSpeechSynthesisProvider(command=command)
        handle = await provider.speak(SpeechRequest(segments=(SpeechSegment(cue="confirmation"),)))
        await handle.wait()
        assert observed[0].cue == "confirmation"


class TestSynthesisService:
    async def test_speaks_only_bounded_persona_spoken_response(self) -> None:
        requests: list[SpeechRequest] = []

        class Provider:
            async def speak(self, request: SpeechRequest):  # type: ignore[no-untyped-def]
                requests.append(request)
                return None

            async def interrupt(self) -> bool:
                return False

        service = SpeechSynthesisService(Provider())  # type: ignore[arg-type]
        await service.speak(SpokenResponse(text="The workspace is ready."))
        assert requests[0].segments[0].text == "The workspace is ready."

    @pytest.mark.parametrize(
        "text",
        [
            "Read /Users/aditya1981/.ssh/id_ed25519 aloud.",
            "The authorization token is sk-secret-value.",
            "password=hunter2",
        ],
    )
    async def test_secret_or_secure_path_is_not_spoken(self, text: str) -> None:
        requests: list[SpeechRequest] = []

        class Provider:
            async def speak(self, request: SpeechRequest):  # type: ignore[no-untyped-def]
                requests.append(request)
                return None

            async def interrupt(self) -> bool:
                return False

        service = SpeechSynthesisService(Provider())  # type: ignore[arg-type]
        await service.speak(SpokenResponse(text=text))
        spoken = requests[0].segments[0].text
        assert "aditya1981" not in spoken
        assert "secret" not in spoken.lower()
        assert "hunter2" not in spoken
        assert spoken == "Sensitive details are available in the display."


async def test_piper_missing_binary_or_model_is_typed_unavailable(tmp_path: Path) -> None:
    provider = PiperSpeechSynthesisProvider(
        executable=tmp_path / "missing-piper",
        model_path=tmp_path / "missing-voice.onnx",
    )
    health = await provider.health()
    assert health.available is False
    with pytest.raises(SpeechSynthesisUnavailable):
        await provider.speak(SpeechRequest(segments=(SpeechSegment(text="hello"),)))
