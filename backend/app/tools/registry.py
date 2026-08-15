"""
Central catalog of every tool the agent can call, each tagged "safe" (runs
immediately) or "confirm" (needs the operator's on-screen approval first),
per the safety rules in PLAN.md section 6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from app.tools import apps, browser, datetime_tool, files, screen, system_control, whatsapp


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Any]
    safety: str  # "safe" | "confirm"
    summarize: Callable[[dict], str] | None = None
    validate: Callable[[dict], None] | None = None


def _whatsapp_summary(args: dict) -> str:
    target = args.get("phone") or args.get("name") or "unknown recipient"
    return f"Send \"{args.get('message', '')}\" to {target}?"


def _validate_whatsapp(args: dict) -> None:
    # Models sometimes fabricate a plausible-looking or placeholder number
    # ("+9188XXXXXXX", "<user's phone number>") rather than asking for the
    # real one. Reject anything that isn't just digits (with an optional
    # leading +) before it ever reaches a confirm card.
    phone = args.get("phone")
    if phone and not re.fullmatch(r"\+?\d{7,15}", phone.strip()):
        raise ValueError(
            f"'{phone}' is not a real phone number the operator provided — it looks "
            "guessed or placeholder text. Ask the operator for their actual number "
            "in plain text; do not call this tool again until they give you one."
        )


def _write_file_summary(args: dict) -> str:
    return f"Write to file '{args.get('relative_path')}'?"


def _delete_file_summary(args: dict) -> str:
    return f"Delete file '{args.get('relative_path')}'?"


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="open_app",
        description="Open an installed Windows application by name (fuzzy match).",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=apps.open_app,
        safety="safe",
    ),
    ToolSpec(
        name="close_app",
        description="Close a running application by name (fuzzy match against running processes).",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=apps.close_app,
        safety="safe",
    ),
    ToolSpec(
        name="list_apps",
        description="List every installed application NEXUS can open.",
        parameters={"type": "object", "properties": {}},
        handler=apps.list_apps,
        safety="safe",
    ),
    ToolSpec(
        name="get_current_time",
        description="Get the current date and time on the operator's PC.",
        parameters={"type": "object", "properties": {}},
        handler=datetime_tool.get_current_time,
        safety="safe",
    ),
    ToolSpec(
        name="whatsapp_send",
        description=(
            "Send a WhatsApp message to a contact by phone number or name. "
            "Provide 'phone' (with country code, or a plain 10-digit Indian "
            "number) or 'name', plus 'message'. Only call this with a phone "
            "number or name the operator actually typed in this conversation "
            "— if they said something like 'my own number' without ever "
            "giving you the digits, do not call this tool; ask them for the "
            "number in plain text instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "phone": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["message"],
        },
        handler=whatsapp.whatsapp_send,
        safety="confirm",
        summarize=_whatsapp_summary,
        validate=_validate_whatsapp,
    ),
    ToolSpec(
        name="volume_up",
        description="Increase the system volume.",
        parameters={"type": "object", "properties": {"steps": {"type": "integer"}}},
        handler=system_control.volume_up,
        safety="safe",
    ),
    ToolSpec(
        name="volume_down",
        description="Decrease the system volume.",
        parameters={"type": "object", "properties": {"steps": {"type": "integer"}}},
        handler=system_control.volume_down,
        safety="safe",
    ),
    ToolSpec(
        name="mute",
        description="Mute or unmute system audio.",
        parameters={"type": "object", "properties": {"unmute": {"type": "boolean"}}},
        handler=system_control.mute,
        safety="safe",
    ),
    ToolSpec(
        name="lock_screen",
        description="Lock the Windows session.",
        parameters={"type": "object", "properties": {}},
        handler=system_control.lock_screen,
        safety="safe",
    ),
    ToolSpec(
        name="open_url",
        description="Open a URL in the default browser.",
        parameters={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        handler=browser.open_url,
        safety="safe",
    ),
    ToolSpec(
        name="web_search",
        description="Search the web for a query in the default browser.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        handler=browser.web_search,
        safety="safe",
    ),
    ToolSpec(
        name="take_screenshot",
        description="Take a screenshot of the screen and return it as base64 PNG.",
        parameters={"type": "object", "properties": {}},
        handler=screen.screenshot_base64,
        safety="safe",
    ),
    ToolSpec(
        name="read_text_on_screen",
        description="OCR the current screen and return the text found on it.",
        parameters={"type": "object", "properties": {}},
        handler=screen.read_text_on_screen,
        safety="safe",
    ),
    ToolSpec(
        name="list_dir",
        description="List files in a directory relative to the sandboxed file root.",
        parameters={"type": "object", "properties": {"relative_path": {"type": "string"}}},
        handler=files.list_dir,
        safety="safe",
    ),
    ToolSpec(
        name="read_file",
        description="Read a text file relative to the sandboxed file root.",
        parameters={
            "type": "object",
            "properties": {"relative_path": {"type": "string"}},
            "required": ["relative_path"],
        },
        handler=files.read_file,
        safety="safe",
    ),
    ToolSpec(
        name="write_file",
        description="Write text to a file relative to the sandboxed file root.",
        parameters={
            "type": "object",
            "properties": {
                "relative_path": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
            "required": ["relative_path", "content"],
        },
        handler=files.write_file,
        safety="confirm",
        summarize=_write_file_summary,
    ),
    ToolSpec(
        name="delete_file",
        description="Delete a file relative to the sandboxed file root.",
        parameters={
            "type": "object",
            "properties": {"relative_path": {"type": "string"}},
            "required": ["relative_path"],
        },
        handler=files.delete_file,
        safety="confirm",
        summarize=_delete_file_summary,
    ),
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}
