"""
Text-to-speech via edge-tts (free, decent quality, needs internet). Returns
None on any failure rather than raising — TTS is a nice-to-have, and the
caller falls back to the browser's built-in speechSynthesis so NEXUS never
goes silent (PLAN.md section 7).
"""

from __future__ import annotations

import edge_tts

DEFAULT_VOICE = "en-US-GuyNeural"


async def synthesize(text: str, voice: str = DEFAULT_VOICE) -> bytes | None:
    if not text.strip():
        return None
    try:
        communicate = edge_tts.Communicate(text, voice)
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
        return bytes(audio) if audio else None
    except Exception:  # noqa: BLE001 - fall back to the browser voice instead of erroring
        return None
