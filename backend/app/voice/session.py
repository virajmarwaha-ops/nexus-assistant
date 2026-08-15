"""
Per-connection voice pipeline: continuously scores incoming audio for the
wake word, records the utterance that follows (stopping itself once you go
quiet), transcribes it, runs it through the same agent loop as typed chat,
and speaks the reply back. Talking while NEXUS is speaking interrupts it
(barge-in) and starts a new utterance immediately.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from enum import Enum
from typing import Awaitable, Callable

import numpy as np

from app.agent import AgentResult, start_agent
from app.voice import stt, tts, wake_word

logger = logging.getLogger("nexus.voice")

SAMPLE_RATE = 16000
WAKE_THRESHOLD = 0.5
SILENCE_RMS_THRESHOLD = 300
BARGE_IN_RMS_THRESHOLD = SILENCE_RMS_THRESHOLD * 2

# Thresholds are tracked in audio sample counts rather than wall-clock time —
# that's what they're meant to measure (how much of what was actually said
# was silence), and it keeps this logic deterministic under processing/
# network jitter instead of drifting with how fast frames happen to arrive.
SILENCE_DURATION_SAMPLES = int(0.9 * SAMPLE_RATE)
MAX_UTTERANCE_SAMPLES = int(12.0 * SAMPLE_RATE)
MIN_UTTERANCE_SAMPLES = int(0.3 * SAMPLE_RATE)

SendEvent = Callable[[dict], Awaitable[None]]


class _State(Enum):
    IDLE = "idle"  # listening for the wake word
    LISTENING = "listening"  # recording an utterance
    PROCESSING = "processing"  # STT + agent running
    SPEAKING = "speaking"  # playing a reply, watching for barge-in


class VoiceSession:
    def __init__(self, send_event: SendEvent, provider: str = "groq", model: str | None = None) -> None:
        self._send = send_event
        self._provider = provider
        self._model = model
        self._state = _State.IDLE
        self._wake_buffer = np.empty(0, dtype=np.int16)
        self._utterance = bytearray()
        self._utterance_samples = 0
        self._quiet_samples = 0
        self._diag_frames = 0
        self._diag_max_rms = 0.0
        self._diag_max_score = 0.0

    async def feed_audio(self, pcm_bytes: bytes) -> None:
        chunk = np.frombuffer(pcm_bytes, dtype=np.int16)
        if len(chunk) == 0:
            return

        self._diag_frames += 1
        self._diag_max_rms = max(self._diag_max_rms, self._rms(chunk))
        if self._diag_frames % 40 == 0:
            logger.info(
                "audio diag: %d frames, max_rms=%.1f, max_wake_score=%.3f, state=%s",
                self._diag_frames,
                self._diag_max_rms,
                self._diag_max_score,
                self._state,
            )
            self._diag_max_rms = 0.0
            self._diag_max_score = 0.0

        if self._state == _State.IDLE:
            await self._feed_wake(chunk)
        elif self._state == _State.LISTENING:
            await self._feed_listening(chunk)
        elif self._state == _State.SPEAKING:
            await self._feed_barge_in(chunk)
        # PROCESSING: drop audio, we're between turns

    async def notify_playback_done(self) -> None:
        if self._state == _State.SPEAKING:
            self._state = _State.IDLE

    @staticmethod
    def _rms(chunk: np.ndarray) -> float:
        return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))

    async def _feed_wake(self, chunk: np.ndarray) -> None:
        self._wake_buffer = np.concatenate([self._wake_buffer, chunk])
        while len(self._wake_buffer) >= wake_word.CHUNK_SAMPLES:
            frame = self._wake_buffer[: wake_word.CHUNK_SAMPLES]
            self._wake_buffer = self._wake_buffer[wake_word.CHUNK_SAMPLES :]
            confidence = await asyncio.to_thread(wake_word.score, frame)
            self._diag_max_score = max(self._diag_max_score, confidence)
            if confidence >= WAKE_THRESHOLD:
                await self._start_listening()
                return

    async def _start_listening(self) -> None:
        logger.info("wake word detected, listening")
        self._state = _State.LISTENING
        self._utterance = bytearray()
        self._utterance_samples = 0
        self._quiet_samples = 0
        await self._send({"type": "wake"})

    async def _feed_listening(self, chunk: np.ndarray) -> None:
        self._utterance.extend(chunk.tobytes())
        self._utterance_samples += len(chunk)

        if self._rms(chunk) > SILENCE_RMS_THRESHOLD:
            self._quiet_samples = 0
        else:
            self._quiet_samples += len(chunk)

        long_enough = self._utterance_samples >= MIN_UTTERANCE_SAMPLES
        gone_quiet = self._quiet_samples >= SILENCE_DURATION_SAMPLES
        too_long = self._utterance_samples >= MAX_UTTERANCE_SAMPLES

        if too_long or (long_enough and gone_quiet):
            await self._finish_utterance()

    async def _finish_utterance(self) -> None:
        duration_s = self._utterance_samples / SAMPLE_RATE
        logger.info("utterance finished: %.2fs of audio, transcribing", duration_s)
        self._state = _State.PROCESSING
        pcm_bytes = bytes(self._utterance)
        self._utterance = bytearray()
        self._wake_buffer = np.empty(0, dtype=np.int16)

        await self._send({"type": "thinking"})

        try:
            text = await asyncio.to_thread(stt.transcribe, pcm_bytes, SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001
            logger.exception("STT failed")
            await self._send({"type": "error", "message": str(exc)})
            self._state = _State.IDLE
            return

        if not text:
            logger.info("STT returned empty text")
            await self._send({"type": "error", "message": "Didn't catch that — try again."})
            self._state = _State.IDLE
            return

        logger.info("transcript: %r", text)
        await self._send({"type": "transcript", "text": text})

        try:
            result = await asyncio.to_thread(start_agent, text, self._provider, self._model)
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent call failed")
            await self._send({"type": "error", "message": str(exc)})
            self._state = _State.IDLE
            return

        await self._emit_agent_result(result)

    async def _emit_agent_result(self, result: AgentResult) -> None:
        if result.kind == "confirm":
            confirmation = result.confirmation
            assert confirmation is not None
            logger.info("agent wants confirmation: %s", confirmation.summary)
            await self._send(
                {
                    "type": "confirm",
                    "confirmation_id": confirmation.confirmation_id,
                    "tool_name": confirmation.tool_name,
                    "summary": confirmation.summary,
                    "arguments": confirmation.arguments,
                }
            )
            # The confirm card is resolved over the existing REST endpoint; go
            # back to listening for the wake word rather than blocking here.
            self._state = _State.IDLE
            return

        await self.speak(result.reply or "")

    async def speak(self, text: str) -> None:
        self._state = _State.SPEAKING
        audio = await tts.synthesize(text)
        logger.info("speaking reply (%s): %r", "tts audio" if audio else "browser fallback", text)
        await self._send(
            {
                "type": "reply",
                "text": text,
                "audio_base64": base64.b64encode(audio).decode("ascii") if audio else None,
            }
        )

    async def _feed_barge_in(self, chunk: np.ndarray) -> None:
        if self._rms(chunk) > BARGE_IN_RMS_THRESHOLD:
            await self._send({"type": "barge_in"})
            await self._start_listening()
