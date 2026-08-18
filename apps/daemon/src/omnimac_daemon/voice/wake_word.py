"""Wake word engine using openwakeword."""

import logging

import numpy as np

logger = logging.getLogger(__name__)


class WakeWordEngine:
    def __init__(self, models: list[str] | None = None) -> None:
        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError("openwakeword is not installed") from exc

        if models is None:
            models = ["hey_jarvis"]

        self.model = Model(wakeword_models=models, inference_framework="onnx")
        self.target_word = models[0] if models else ""

    def process_chunk(self, audio_chunk: bytes) -> bool:
        """Process 16kHz mono PCM (s16le) audio chunk and return True if wake word detected."""
        if not audio_chunk:
            return False

        # Convert raw bytes to int16 numpy array
        # openwakeword expects 16kHz 16-bit audio
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16)

        preds = self.model.predict(audio_array)

        # openwakeword uses a threshold (usually ~0.5) to determine detection
        for wakeword, score in preds.items():
            if score > 0.5:
                logger.info(f"Wake word '{wakeword}' detected! (score: {score:.2f})")
                return True

        return False
