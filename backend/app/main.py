"""
NEXUS backend entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import base64
import json
import logging

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent import AgentResult, resume_agent, start_agent
from app.checklist import run_checklist
from app.config import settings
from app.llm_providers import LLMError
from app.voice import tts
from app.voice.session import VoiceSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="NEXUS Assistant API", version="1.0.0")

# The Electron/React frontend runs on a different origin in dev; relax CORS
# for localhost only. Tighten this before exposing the API elsewhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    provider: str = "groq"
    model: str | None = None


class ConfirmRequest(BaseModel):
    confirmation_id: str
    approved: bool


class ChatResponse(BaseModel):
    type: str  # "reply" | "confirm"
    reply: str | None = None
    confirmation_id: str | None = None
    tool_name: str | None = None
    summary: str | None = None
    arguments: dict | None = None


class TTSRequest(BaseModel):
    text: str


class TTSResponse(BaseModel):
    audio_base64: str | None = None


class ChecklistItem(BaseModel):
    id: str
    label: str
    ok: bool
    hint: str


def _to_response(result: AgentResult) -> ChatResponse:
    if result.kind == "reply":
        return ChatResponse(type="reply", reply=result.reply)
    confirmation = result.confirmation
    assert confirmation is not None
    return ChatResponse(
        type="confirm",
        confirmation_id=confirmation.confirmation_id,
        tool_name=confirmation.tool_name,
        summary=confirmation.summary,
        arguments=confirmation.arguments,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.nexus_env}


@app.get("/system/checklist", response_model=list[ChecklistItem])
def checklist_endpoint() -> list[dict]:
    return run_checklist()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    One socket, two jobs: it's the connected/disconnected signal for the
    orb, and — once the frontend starts streaming mic audio as binary
    frames — the transport for the whole wake-word/listen/speak voice loop.
    Text frames carry JSON control messages (e.g. "playback_done").
    """
    await websocket.accept()
    await websocket.send_json({"type": "connected"})

    session = VoiceSession(send_event=websocket.send_json)

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            audio = message.get("bytes")
            if audio is not None:
                await session.feed_audio(audio)
                continue

            text = message.get("text")
            if text is None:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "playback_done":
                await session.notify_playback_done()
    except WebSocketDisconnect:
        pass


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    try:
        result = start_agent(user_message=payload.message, provider=payload.provider, model=payload.model)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(result)


@app.post("/chat/confirm", response_model=ChatResponse)
def confirm_endpoint(payload: ConfirmRequest) -> ChatResponse:
    try:
        result = resume_agent(payload.confirmation_id, payload.approved)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(result)


@app.post("/tts", response_model=TTSResponse)
async def tts_endpoint(payload: TTSRequest) -> TTSResponse:
    """Used by the frontend to speak a reply that arrived outside the voice
    websocket loop (e.g. after resolving a voice-triggered confirm card via
    the REST /chat/confirm endpoint)."""
    audio = await tts.synthesize(payload.text)
    return TTSResponse(audio_base64=base64.b64encode(audio).decode("ascii") if audio else None)
