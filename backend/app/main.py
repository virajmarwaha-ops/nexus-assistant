"""
NEXUS backend entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent import run_agent
from app.auth import create_access_token, get_current_subject
from app.config import settings

app = FastAPI(title="NEXUS Assistant API", version="1.0.0")

# The Electron/React frontend runs on a different origin in dev; relax CORS
# for localhost only. Tighten this before exposing the API elsewhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    passphrase: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChatRequest(BaseModel):
    message: str
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.nexus_env}


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    # Single-operator local auth: compare against the shared secret in .env.
    # Swap this for real user management before running multi-user.
    if payload.passphrase != settings.jwt_secret:
        raise HTTPException(status_code=401, detail="Invalid passphrase")
    token = create_access_token(subject="operator")
    return LoginResponse(access_token=token)


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    payload: ChatRequest,
    subject: str = Depends(get_current_subject),
) -> ChatResponse:
    reply = run_agent(
        user_message=payload.message,
        provider=payload.provider,
        model=payload.model,
    )
    return ChatResponse(reply=reply)
