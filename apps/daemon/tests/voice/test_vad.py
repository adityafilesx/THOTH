from omnimac_daemon.voice.contracts import VoiceActivityState
from omnimac_daemon.voice.vad import PCMVoiceActivityDetector


def test_pcm_vad_distinguishes_speech_from_silence() -> None:
    detector = PCMVoiceActivityDetector(rms_threshold=500)
    silence = b"\x00\x00" * 160
    speech = (2_000).to_bytes(2, "little", signed=True) * 160
    assert detector.classify(silence) is VoiceActivityState.SILENCE
    assert detector.classify(speech) is VoiceActivityState.SPEAKING


def test_pcm_vad_fails_closed_on_invalid_frame() -> None:
    detector = PCMVoiceActivityDetector()
    assert detector.classify(b"") is VoiceActivityState.SILENCE
    assert detector.classify(b"\x01") is VoiceActivityState.SILENCE
