"""
Minimal agent orchestration loop: sends the conversation to an LLM provider,
executes any tool calls it requests, feeds the results back, and repeats
until the model returns a plain text answer (or a turn limit is hit).
"""

from __future__ import annotations

from typing import Any, Callable

from app.llm_providers import chat
from app.tools import files, input_control, screen

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "read_text_on_screen": screen.read_text_on_screen,
    "find_text_location": screen.find_text_location,
    "move_mouse": input_control.move_mouse,
    "click": input_control.click,
    "type_text": input_control.type_text,
    "press_key": input_control.press_key,
    "hotkey": input_control.hotkey,
    "list_dir": files.list_dir,
    "read_file": files.read_file,
    "write_file": files.write_file,
}

# Anthropic-style tool schemas. Adjust/extend as you add tools.
TOOL_SCHEMAS = [
    {
        "name": "read_text_on_screen",
        "description": "OCR the current screen and return the text found on it.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "click",
        "description": "Click the mouse at the given screen coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text using the keyboard at the current cursor/focus position.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "list_dir",
        "description": "List files in a directory relative to the sandboxed file root.",
        "input_schema": {
            "type": "object",
            "properties": {"relative_path": {"type": "string"}},
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file relative to the sandboxed file root.",
        "input_schema": {
            "type": "object",
            "properties": {"relative_path": {"type": "string"}},
            "required": ["relative_path"],
        },
    },
]

MAX_TURNS = 8


def run_tool(name: str, arguments: dict) -> Any:
    handler = TOOL_REGISTRY.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return handler(**arguments)
    except Exception as exc:  # noqa: BLE001 - surface the error to the model, don't crash
        return {"error": str(exc)}


def run_agent(
    user_message: str,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    system_prompt: str = "You are NEXUS, a helpful desktop assistant.",
) -> str:
    """Run the tool-use loop for a single user turn and return the final text reply."""
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TURNS):
        result = chat(
            messages=[{"role": "system", "content": system_prompt}, *messages],
            provider=provider,
            model=model,
            tools=TOOL_SCHEMAS,
        )

        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            return result.get("content") or ""

        messages.append({"role": "assistant", "content": result.get("content") or ""})

        for call in tool_calls:
            name = call.get("name") or call.get("function", {}).get("name")
            arguments = call.get("input") or call.get("arguments") or {}
            tool_output = run_tool(name, arguments)
            messages.append(
                {"role": "user", "content": f"[tool result: {name}] {tool_output}"}
            )

    return "I hit my step limit for this task — let me know if you'd like me to continue."
