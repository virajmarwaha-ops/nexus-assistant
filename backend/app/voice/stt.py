"""
Speech-to-text via Groq's hosted Whisper endpoint (whisper-large-v3-turbo) —
cheap and fast enough to keep the voice loop responsive, per PLAN.md
section 7's "money-saving option".
"""

from __future__ import annotations

import io
import wave

from app.config import settings
from app.llm_providers import LLMError


def transcribe(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set")

    from openai import OpenAI

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)

    client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    try:
        response = client.audio.transcriptions.create(
            file=("utterance.wav", buffer.getvalue(), "audio/wav"),
            model="whisper-large-v3-turbo",
            # Without a language hint, Whisper sometimes hallucinates text in
            # an unrelated language on quiet/unclear audio (seen: transcribed
            # near-silence as Russian) — pin it to English.
            language="en",
        )
    except Exception as exc:  # noqa: BLE001 - surface as a clean LLMError, not a 500
        raise LLMError(f"Transcription failed: {exc}") from exc
    return response.text.strip()
