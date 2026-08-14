"""
Thin wrapper that gives the rest of the app a single, provider-agnostic
`chat(...)` call regardless of which backend (OpenAI, Anthropic, Gemini,
or a local Ollama/vLLM server) is configured.
"""

from __future__ import annotations

from typing import Any

from app.config import settings

ChatMessage = dict[str, Any]


class LLMError(RuntimeError):
    pass


def _chat_openai(messages: list[ChatMessage], model: str, tools: list[dict] | None) -> dict:
    from openai import OpenAI

    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools or None,
    )
    choice = response.choices[0].message
    return {
        "content": choice.content,
        "tool_calls": [tc.model_dump() for tc in (choice.tool_calls or [])],
    }


def _chat_anthropic(messages: list[ChatMessage], model: str, tools: list[dict] | None) -> dict:
    import anthropic

    if not settings.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=messages,
        tools=tools or [],
    )
    text_blocks = [b.text for b in response.content if b.type == "text"]
    tool_blocks = [b.model_dump() for b in response.content if b.type == "tool_use"]
    return {"content": "\n".join(text_blocks), "tool_calls": tool_blocks}


def _chat_local(messages: list[ChatMessage], model: str, tools: list[dict] | None) -> dict:
    """Talk to a local OpenAI-compatible server (e.g. Ollama, vLLM)."""
    from openai import OpenAI

    client = OpenAI(base_url=settings.local_llm_url, api_key="not-needed")
    response = client.chat.completions.create(
        model=model or settings.local_model,
        messages=messages,
        tools=tools or None,
    )
    choice = response.choices[0].message
    return {
        "content": choice.content,
        "tool_calls": [tc.model_dump() for tc in (choice.tool_calls or [])],
    }


PROVIDERS = {
    "openai": _chat_openai,
    "anthropic": _chat_anthropic,
    "local": _chat_local,
}


def chat(
    messages: list[ChatMessage],
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    tools: list[dict] | None = None,
) -> dict:
    """
    Route a chat request to the configured provider.

    Returns: {"content": str | None, "tool_calls": list[dict]}
    """
    handler = PROVIDERS.get(provider)
    if handler is None:
        raise LLMError(f"Unknown provider '{provider}'. Options: {list(PROVIDERS)}")
    return handler(messages, model, tools)
