"""
Thin wrapper that gives the rest of the app a single, provider-agnostic
`chat(...)` call regardless of which backend (Groq, OpenAI, Anthropic, or
a local Ollama/vLLM server) is configured.

Conversation turns are passed around in a neutral shape so the agent loop
never has to know which wire format a provider speaks:

    {"role": "user", "content": "..."}
    {"role": "assistant", "content": "..." | None, "tool_calls": [{"id", "name", "arguments"}]}
    {"role": "tool", "tool_call_id": "...", "name": "...", "content": ...}

Tool schemas are passed in plain JSON-Schema shape:

    {"name": ..., "description": ..., "parameters": {"type": "object", ...}}

Each provider adapter below translates that neutral shape to/from its own
wire format — this is what was missing before: the old code fed Anthropic
its system prompt as a regular message (which Anthropic rejects) and fed
tool results back as plain chat text instead of proper tool-result blocks
(which confuses the model mid tool-use).
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.config import settings

NeutralMessage = dict[str, Any]
ToolSchema = dict[str, Any]


class LLMError(RuntimeError):
    pass


# Groq's Llama models occasionally emit a tool call as raw pseudo-XML text
# instead of a structured tool_call, which Groq's own API then rejects with
# a 400 "tool_use_failed" error. The intended call is still recoverable from
# the error's `failed_generation` field, but the punctuation around it is
# inconsistent — observed shapes include `<function=name({...})></function>`,
# `<function=name={...}></function>`, `<function=name{...}></function>`, and
# `<function=name({...})</function>` (no closing `>`). Rather than try to
# match every punctuation variant, just find the function name and the first
# `{...}` JSON blob independently and ignore whatever's between/around them.
_FUNCTION_NAME_RE = re.compile(r"<function=([\w.-]+)")
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _recover_malformed_tool_call(exc: Exception) -> dict | None:
    # openai-python's error body shape isn't worth pinning down exactly (it's
    # shifted before), so just prefer the parsed failed_generation field when
    # we can find it and otherwise fall back to the exception's own text —
    # the regexes below are specific enough not to false-positive on
    # unrelated errors.
    body = getattr(exc, "body", None)
    generation = None
    if isinstance(body, dict):
        generation = body.get("failed_generation") or body.get("error", {}).get("failed_generation")
    generation = generation or str(exc)

    name_match = _FUNCTION_NAME_RE.search(generation)
    json_match = _JSON_OBJECT_RE.search(generation)
    if not name_match or not json_match:
        return None

    try:
        arguments = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return None

    return {
        "content": None,
        "tool_calls": [
            {"id": f"recovered-{uuid.uuid4().hex[:8]}", "name": name_match.group(1), "arguments": arguments}
        ],
    }


# --- OpenAI-compatible providers (Groq, OpenAI, local Ollama/vLLM) ---------

def _openai_style_tools(tools: list[ToolSchema] | None) -> list[dict] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def _to_openai_messages(system_prompt: str, messages: list[NeutralMessage]) -> list[dict]:
    wire: list[dict] = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        role = msg["role"]
        if role == "user":
            wire.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            entry: dict = {"role": "assistant", "content": msg.get("content") or None}
            if msg.get("tool_calls"):
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                    }
                    for tc in msg["tool_calls"]
                ]
            wire.append(entry)
        elif role == "tool":
            wire.append(
                {"role": "tool", "tool_call_id": msg["tool_call_id"], "content": str(msg["content"])}
            )
    return wire


def _from_openai_message(message: Any) -> dict:
    tool_calls = [
        {
            "id": tc.id,
            "name": tc.function.name,
            "arguments": json.loads(tc.function.arguments or "{}"),
        }
        for tc in (message.tool_calls or [])
    ]
    return {"content": message.content, "tool_calls": tool_calls}


def _chat_openai_compatible(
    messages: list[NeutralMessage],
    system_prompt: str,
    model: str,
    tools: list[ToolSchema] | None,
    *,
    api_key: str | None,
    base_url: str | None,
    missing_key_error: str,
    fallback_model: str | None = None,
) -> dict:
    import openai
    from openai import OpenAI

    if not api_key:
        raise LLMError(missing_key_error)

    # max_retries=0: the SDK's default backoff can wait 10s+ before even
    # raising, which just delays our own immediate fallback-model retry below.
    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=_to_openai_messages(system_prompt, messages),
            tools=_openai_style_tools(tools),
        )
    except openai.RateLimitError as exc:
        # Free-tier daily quotas are per-model, so a rate-limited primary
        # model doesn't mean a smaller one on the same account is also out —
        # silently retry once on the fallback rather than failing the turn.
        if fallback_model and fallback_model != model:
            return _chat_openai_compatible(
                messages,
                system_prompt,
                fallback_model,
                tools,
                api_key=api_key,
                base_url=base_url,
                missing_key_error=missing_key_error,
            )
        raise LLMError(f"Model request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - surface provider hiccups as a clean LLMError, not a 500
        recovered = _recover_malformed_tool_call(exc)
        if recovered is not None:
            return recovered
        raise LLMError(f"Model request failed: {exc}") from exc
    return _from_openai_message(response.choices[0].message)


GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"


def _chat_groq(messages: list[NeutralMessage], system_prompt: str, model: str, tools: list[ToolSchema] | None) -> dict:
    return _chat_openai_compatible(
        messages,
        system_prompt,
        model,
        tools,
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        missing_key_error="GROQ_API_KEY is not set",
        fallback_model=GROQ_FALLBACK_MODEL,
    )


def _chat_openai(messages: list[NeutralMessage], system_prompt: str, model: str, tools: list[ToolSchema] | None) -> dict:
    return _chat_openai_compatible(
        messages,
        system_prompt,
        model,
        tools,
        api_key=settings.openai_api_key,
        base_url=None,
        missing_key_error="OPENAI_API_KEY is not set",
    )


def _chat_local(messages: list[NeutralMessage], system_prompt: str, model: str, tools: list[ToolSchema] | None) -> dict:
    return _chat_openai_compatible(
        messages,
        system_prompt,
        model,
        tools,
        api_key="not-needed",
        base_url=settings.local_llm_url,
        missing_key_error="unreachable",
    )


# --- Anthropic --------------------------------------------------------------

def _to_anthropic_messages(messages: list[NeutralMessage]) -> list[dict]:
    wire: list[dict] = []
    pending_tool_results: list[dict] = []

    def flush_tool_results() -> None:
        if pending_tool_results:
            wire.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

    for msg in messages:
        role = msg["role"]
        if role == "user":
            flush_tool_results()
            wire.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            flush_tool_results()
            content: list[dict] = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in msg.get("tool_calls") or []:
                content.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]})
            wire.append({"role": "assistant", "content": content})
        elif role == "tool":
            pending_tool_results.append(
                {"type": "tool_result", "tool_use_id": msg["tool_call_id"], "content": str(msg["content"])}
            )
    flush_tool_results()
    return wire


def _chat_anthropic(messages: list[NeutralMessage], system_prompt: str, model: str, tools: list[ToolSchema] | None) -> dict:
    import anthropic

    if not settings.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=_to_anthropic_messages(messages),
            tools=[
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters") or {"type": "object", "properties": {}},
                }
                for t in (tools or [])
            ],
        )
    except Exception as exc:  # noqa: BLE001 - surface provider hiccups as a clean LLMError, not a 500
        raise LLMError(f"Model request failed: {exc}") from exc
    text_blocks = [b.text for b in response.content if b.type == "text"]
    tool_calls = [
        {"id": b.id, "name": b.name, "arguments": b.input}
        for b in response.content
        if b.type == "tool_use"
    ]
    return {"content": "\n".join(text_blocks) or None, "tool_calls": tool_calls}


# --- Dispatch ----------------------------------------------------------------

PROVIDERS = {
    "groq": _chat_groq,
    "openai": _chat_openai,
    "anthropic": _chat_anthropic,
    "local": _chat_local,
}

DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-6",
    "local": "llama3.2",
}


def chat(
    messages: list[NeutralMessage],
    system_prompt: str,
    provider: str = "groq",
    model: str | None = None,
    tools: list[ToolSchema] | None = None,
) -> dict:
    """
    Route a chat request to the configured provider.

    Returns: {"content": str | None, "tool_calls": list[{"id", "name", "arguments"}]}
    """
    handler = PROVIDERS.get(provider)
    if handler is None:
        raise LLMError(f"Unknown provider '{provider}'. Options: {list(PROVIDERS)}")
    return handler(messages, system_prompt, model or DEFAULT_MODELS[provider], tools)
