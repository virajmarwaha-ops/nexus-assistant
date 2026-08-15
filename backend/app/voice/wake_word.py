"""
"Hey Jarvis" wake-word detection via openWakeWord's ready-made ONNX model —
no training needed, just a pretrained model downloaded once on first use.
Runs entirely on this PC; nothing is sent anywhere until it fires.
"""

from __future__ import annotations

import numpy as np
from openwakeword.model import Model
from openwakeword.utils import download_models

WAKE_WORD = "hey_jarvis"
CHUNK_SAMPLES = 1280  # 80ms at 16kHz — openWakeWord's native frame size

_model: Model | None = None


def _get_model() -> Model:
    global _model
    if _model is None:
        download_models([WAKE_WORD])
        _model = Model(wakeword_models=[WAKE_WORD], inference_framework="onnx")
    return _model


def score(pcm_chunk: np.ndarray) -> float:
    """Score one CHUNK_SAMPLES-length frame of 16kHz mono int16 PCM for the wake word."""
    return float(_get_model().predict(pcm_chunk)[WAKE_WORD])
