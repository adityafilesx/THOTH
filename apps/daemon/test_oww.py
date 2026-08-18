import numpy as np
import openwakeword
from openwakeword.model import Model

# Download models
openwakeword.utils.download_models()

# Load a generic "hey jarvis" model
m = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

# Dummy inference
audio = np.zeros(1280, dtype=np.int16)
preds = m.predict(audio)
print("Predictions:", preds)
