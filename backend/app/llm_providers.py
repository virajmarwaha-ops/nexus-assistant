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
# the error's `failed_generation` field, in one of two shapes seen in
# practice: `<function=name({...})></function>` or `<function=name={...}>
# </function>`. Rather than surface that as a hard failure, parse it back
# into a normal tool call.
_MALFORMED_TOOL_CALL_PATTERNS = [
    re.compile(r"<function=([\w.-]+)\((.*)\)></function>", re.DOTALL),
    re.compile(r"<function=([\w.-]+)=(.*)></function>", re.DOTALL),
]


def _recover_malformed_tool_call(exc: Exception) -> dict | None:
    body = getattr(exc, "body", None)
    error = body.get("error", {}) if isinstance(body, dict) else {}
    if error.get("code") != "tool_use_failed":
        return None

    generation = error.get("failed_generation") or str(exc)
    for pattern in _MALFORMED_TOOL_CALL_PATTERNS:
        match = pattern.search(generation)
        if not match:
            continue
        name, raw_args = match.group(1), match.group(2)
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError:
            continue
        return {
            "content": None,
            "tool_calls": [{"id": f"recovered-{uuid.uuid4().hex[:8]}", "name": name, "arguments": arguments}],
        }
    return None


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
) -> dict:
    from openai import OpenAI

    if not api_key:
        raise LLMError(missing_key_error)

    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=_to_openai_messages(system_prompt, messages),
            tools=_openai_style_tools(tools),
        )
    except Exception as exc:  # noqa: BLE001 - surface provider hiccups as a clean LLMError, not a 500
        recovered = _recover_malformed_tool_call(exc)
        if recovered is not None:
            return recovered
        raise LLMError(f"Model request failed: {exc}") from exc
    return _from_openai_message(response.choices[0].message)


def _chat_groq(messages: list[NeutralMessage], system_prompt: str, model: str, tools: list[ToolSchema] | None) -> dict:
    return _chat_openai_compatible(
        messages,
        system_prompt,
        model,
        tools,
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        missing_key_error="GROQ_API_KEY is not set",
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
