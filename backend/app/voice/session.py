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
import time
from enum import Enum
from typing import Awaitable, Callable

import numpy as np

from app.agent import AgentResult, PendingConfirmation, resume_agent, start_agent
from app.voice import stt, tts, wake_word

logger = logging.getLogger("nexus.voice")

SAMPLE_RATE = 16000
# The false-positive firing was actually caused by echo/barge-in (see the
# cooldown/grace-period below), not an insufficiently strict threshold —
# raising this to 0.7 just made genuine "hey jarvis" utterances through a
# real mic (peaking well under that in practice) harder to detect than the
# openWakeWord's own 0.5 default. Back to 0.5.
WAKE_THRESHOLD = 0.5

# After NEXUS finishes speaking, the mic can still pick up the tail of its
# own voice through the speakers (echo cancellation isn't perfect, and a
# synthesized voice apparently scores high enough to look like a genuine
# wake word to the model) — briefly ignore audio for wake-word purposes
# right after playback ends so that echo can't re-trigger a new "turn". 1.5s
# wasn't enough margin in a real (presumably echo-prone) room; widened to 3s.
WAKE_COOLDOWN_S = 3.0

# Whisper is well known to hallucinate short filler phrases ("thank you",
# "thanks for watching") when given near-silent/unclear audio rather than
# returning nothing — so a captured "utterance" that's mostly silence (e.g.
# a wake trigger off echo, capturing little to no real speech after it)
# should just be dropped before it ever reaches STT, not transcribed.
MIN_UTTERANCE_RMS = 150

# A human can't physically react and start talking within a few hundred ms
# of NEXUS starting to speak, so any barge-in-level volume that early is
# NEXUS's own voice bleeding into the mic, not a deliberate interruption.
BARGE_IN_GRACE_S = 1.0

SILENCE_RMS_THRESHOLD = 300
BARGE_IN_RMS_THRESHOLD = SILENCE_RMS_THRESHOLD * 2

# Thresholds are tracked in audio sample counts rather than wall-clock time —
# that's what they're meant to measure (how much of what was actually said
# was silence), and it keeps this logic deterministic under processing/
# network jitter instead of drifting with how fast frames happen to arrive.
SILENCE_DURATION_SAMPLES = int(0.9 * SAMPLE_RATE)
MAX_UTTERANCE_SAMPLES = int(12.0 * SAMPLE_RATE)
MIN_UTTERANCE_SAMPLES = int(0.3 * SAMPLE_RATE)

# openWakeWord's embedding model needs a real window of trailing audio to
# build enough confidence to fire, so by the time a wake trigger actually
# registers, the operator has very plausibly already started saying the
# command in the same breath as "hey jarvis" — starting the recording
# buffer completely empty at that moment clips exactly that. Keep a rolling
# pre-roll of recent audio and seed the utterance with it on a genuine wake
# trigger (not on barge-in, where the pre-roll would just be NEXUS's own
# tail-end speech rather than anything the operator said).
PREROLL_SAMPLES = int(1.5 * SAMPLE_RATE)

# Confirm-gated tools (anything with a real-world side effect) get spoken
# aloud and can be answered by voice, not just the on-screen Approve/Deny
# buttons — otherwise a hands-free user has no way to know one is pending.
# Matched by substring against the lowercased transcript rather than an
# exact match, since STT output varies ("Yes.", "yeah go ahead").
_CONFIRM_YES_WORDS = ("yes", "yeah", "yep", "yup", "confirm", "approve", "go ahead", "do it", "sure", "affirmative")
_CONFIRM_NO_WORDS = ("no", "nope", "nah", "cancel", "deny", "don't", "stop", "negative")
MAX_CONFIRMATION_ATTEMPTS = 2

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
        self._wake_cooldown_until = 0.0
        self._speaking_started_at = 0.0
        self._preroll = np.empty(0, dtype=np.int16)
        self._pending_confirmation: PendingConfirmation | None = None
        self._confirmation_attempts = 0

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
            self._preroll = np.concatenate([self._preroll, chunk])[-PREROLL_SAMPLES:]
            await self._feed_wake(chunk)
        elif self._state == _State.LISTENING:
            await self._feed_listening(chunk)
        elif self._state == _State.SPEAKING:
            await self._feed_barge_in(chunk)
        # PROCESSING: drop audio, we're between turns

    async def notify_playback_done(self) -> None:
        if self._state != _State.SPEAKING:
            return
        if self._pending_confirmation is not None:
            # Go straight into listening for the yes/no answer — no wake
            # word needed, this is a direct follow-up to what was just asked.
            await self._start_listening()
        else:
            self._return_to_idle_with_cooldown()

    def _return_to_idle_with_cooldown(self) -> None:
        # Used both after real TTS playback ends and after an error reply
        # (which never plays audio, so never gets a notify_playback_done
        # call) — without this on the error path too, a run of consecutive
        # errors (e.g. a sustained rate limit) re-arms wake detection with
        # zero cooldown each time, letting the same echo/self-trigger issue
        # this cooldown exists for turn into a tight, unbroken error loop.
        self._state = _State.IDLE
        self._wake_cooldown_until = time.monotonic() + WAKE_COOLDOWN_S
        # Discard anything buffered during/right after playback — it may
        # be an echo tail, not something worth scoring once cooldown ends.
        self._wake_buffer = np.empty(0, dtype=np.int16)

    @staticmethod
    def _rms(chunk: np.ndarray) -> float:
        return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))

    async def _feed_wake(self, chunk: np.ndarray) -> None:
        if time.monotonic() < self._wake_cooldown_until:
            return
        self._wake_buffer = np.concatenate([self._wake_buffer, chunk])
        while len(self._wake_buffer) >= wake_word.CHUNK_SAMPLES:
            frame = self._wake_buffer[: wake_word.CHUNK_SAMPLES]
            self._wake_buffer = self._wake_buffer[wake_word.CHUNK_SAMPLES :]
            confidence = await asyncio.to_thread(wake_word.score, frame)
            self._diag_max_score = max(self._diag_max_score, confidence)
            if confidence >= WAKE_THRESHOLD:
                logger.info("wake word detected (score=%.3f), listening", confidence)
                preroll = self._preroll
                self._preroll = np.empty(0, dtype=np.int16)
                await self._start_listening(preroll)
                return

    async def _start_listening(self, preroll: np.ndarray | None = None) -> None:
        self._state = _State.LISTENING
        if preroll is not None and len(preroll):
            self._utterance = bytearray(preroll.tobytes())
            self._utterance_samples = len(preroll)
        else:
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
        pcm_bytes = bytes(self._utterance)
        self._utterance = bytearray()
        self._wake_buffer = np.empty(0, dtype=np.int16)

        utterance_rms = self._rms(np.frombuffer(pcm_bytes, dtype=np.int16))
        if utterance_rms < MIN_UTTERANCE_RMS:
            logger.info(
                "utterance too quiet to bother transcribing (%.2fs, rms=%.1f) — dropping, likely an echo/noise trigger",
                duration_s,
                utterance_rms,
            )
            if self._pending_confirmation is not None:
                await self._retry_or_abandon_confirmation()
            else:
                self._return_to_idle_with_cooldown()
            return

        logger.info("utterance finished: %.2fs of audio, rms=%.1f, transcribing", duration_s, utterance_rms)
        self._state = _State.PROCESSING
        await self._send({"type": "thinking"})

        try:
            text = await asyncio.to_thread(stt.transcribe, pcm_bytes, SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001
            logger.exception("STT failed")
            await self._send({"type": "error", "message": str(exc)})
            if self._pending_confirmation is not None:
                await self._retry_or_abandon_confirmation()
            else:
                self._return_to_idle_with_cooldown()
            return

        if not text:
            logger.info("STT returned empty text")
            await self._send({"type": "error", "message": "Didn't catch that — try again."})
            if self._pending_confirmation is not None:
                await self._retry_or_abandon_confirmation()
            else:
                self._return_to_idle_with_cooldown()
            return

        logger.info("transcript: %r", text)
        await self._send({"type": "transcript", "text": text})

        if self._pending_confirmation is not None:
            await self._resolve_confirmation_from_speech(text)
            return

        try:
            result = await asyncio.to_thread(start_agent, text, self._provider, self._model)
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent call failed")
            await self._send({"type": "error", "message": str(exc)})
            self._return_to_idle_with_cooldown()
            return

        await self._emit_agent_result(result)

    async def _retry_or_abandon_confirmation(self) -> None:
        """Couldn't get a usable answer for a pending voice confirmation."""
        self._confirmation_attempts += 1
        if self._confirmation_attempts >= MAX_CONFIRMATION_ATTEMPTS:
            logger.info("giving up on voice confirmation after %d attempts — left on screen", self._confirmation_attempts)
            self._pending_confirmation = None
            self._confirmation_attempts = 0
            self._return_to_idle_with_cooldown()
            return
        await self.speak("Sorry, I didn't catch that. Yes or no?")

    async def _resolve_confirmation_from_speech(self, text: str) -> None:
        confirmation = self._pending_confirmation
        assert confirmation is not None
        normalized = text.strip().lower().rstrip(".!?")

        approved = any(word in normalized for word in _CONFIRM_YES_WORDS)
        denied = any(word in normalized for word in _CONFIRM_NO_WORDS)

        if approved == denied:  # neither matched, or (unlikely) both did — ambiguous either way
            logger.info("confirmation response %r wasn't a clear yes/no, re-prompting", text)
            await self._retry_or_abandon_confirmation()
            return

        self._pending_confirmation = None
        self._confirmation_attempts = 0

        try:
            result = await asyncio.to_thread(resume_agent, confirmation.confirmation_id, approved)
        except KeyError:
            # Resolved already via the on-screen Approve/Deny buttons before
            # the spoken answer came in — nothing left to do.
            logger.info("confirmation %s already resolved elsewhere", confirmation.confirmation_id)
            self._return_to_idle_with_cooldown()
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("resume_agent failed")
            await self._send({"type": "error", "message": str(exc)})
            self._return_to_idle_with_cooldown()
            return

        await self._send({"type": "confirm_resolved", "confirmation_id": confirmation.confirmation_id})
        await self._emit_agent_result(result)

    async def _emit_agent_result(self, result: AgentResult) -> None:
        if result.kind == "confirm":
            confirmation = result.confirmation
            assert confirmation is not None
            logger.info("agent wants confirmation: %s", confirmation.summary)
            self._pending_confirmation = confirmation
            self._confirmation_attempts = 0
            await self._send(
                {
                    "type": "confirm",
                    "confirmation_id": confirmation.confirmation_id,
                    "tool_name": confirmation.tool_name,
                    "summary": confirmation.summary,
                    "arguments": confirmation.arguments,
                }
            )
            # Speak it too — a hands-free user has no other way to know one's
            # pending. notify_playback_done() routes back into listening for
            # the yes/no once this finishes, since _pending_confirmation is set.
            await self.speak(f"{confirmation.summary} Say yes to confirm, or no to cancel.")
            return

        await self.speak(result.reply or "")

    async def speak(self, text: str) -> None:
        self._state = _State.SPEAKING
        self._speaking_started_at = time.monotonic()
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
        if time.monotonic() - self._speaking_started_at < BARGE_IN_GRACE_S:
            return
        if self._rms(chunk) > BARGE_IN_RMS_THRESHOLD:
            logger.info("barge-in detected, listening")
            await self._send({"type": "barge_in"})
            await self._start_listening()
