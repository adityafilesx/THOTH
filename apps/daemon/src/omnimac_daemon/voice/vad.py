"""Small deterministic PCM16 voice-activity detector.

Compressed-container capture still uses the platform capture VAD. This helper
provides a provider-neutral, dependency-free boundary for raw PCM streams and
tests; it never records or retains audio.
"""

from __future__ import annotations

import math
import sys
from array import array

from omnimac_daemon.voice.contracts import VoiceActivityState


class PCMVoiceActivityDetector:
    def __init__(self, *, rms_threshold: float = 350) -> None:
        if rms_threshold <= 0:
            raise ValueError("rms_threshold must be positive")
        self._threshold = rms_threshold

    def classify(self, pcm16_le: bytes) -> VoiceActivityState:
        if not pcm16_le or len(pcm16_le) % 2:
            return VoiceActivityState.SILENCE
        samples = array("h")
        samples.frombytes(pcm16_le)
        if sys.byteorder != "little":
            samples.byteswap()
        if not samples:
            return VoiceActivityState.SILENCE
        mean_square = sum(sample * sample for sample in samples) / len(samples)
        rms = math.sqrt(mean_square)
        return VoiceActivityState.SPEAKING if rms >= self._threshold else VoiceActivityState.SILENCE
