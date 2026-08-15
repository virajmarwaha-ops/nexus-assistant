"""
NEXUS backend entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent import AgentResult, resume_agent, start_agent
from app.config import settings
from app.llm_providers import LLMError

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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Kept open so the frontend can show a live connected/disconnected dot."""
    await websocket.accept()
    await websocket.send_json({"type": "connected"})
    try:
        while True:
            await websocket.receive_text()
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
