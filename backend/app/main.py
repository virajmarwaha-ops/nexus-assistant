"""
NEXUS backend entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent import run_agent
from app.config import settings

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
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"


class ChatResponse(BaseModel):
    reply: str


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
    reply = run_agent(
        user_message=payload.message,
        provider=payload.provider,
        model=payload.model,
    )
    return ChatResponse(reply=reply)
