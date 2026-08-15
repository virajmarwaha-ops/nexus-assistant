"""
Tool-use agent loop.

Runs the neutral chat loop (see llm_providers.py) against whichever LLM
provider is configured, executing "safe" tools immediately and pausing on
"confirm" tools until the operator approves or denies them — see
PLAN.md section 6 for why that gate exists.

A command that never touches a confirm-tool finishes in one call to
`start_agent`. One that does comes back with an `AgentResult(kind="confirm")`
describing exactly what's about to happen; the caller shows that to the
operator and calls `resume_agent` with their answer to continue.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.llm_providers import chat
from app.tools.registry import TOOLS, TOOLS_BY_NAME

SYSTEM_PROMPT = (
    "You are NEXUS, a helpful desktop assistant running on the operator's own "
    "Windows PC. Use the tools available to you to actually do what's asked "
    "rather than just describing how to do it.\n\n"
    "You have no memory of the operator's personal details — no phone number, "
    "no contact list, nothing — unless they typed it in this exact "
    "conversation. If a request needs a concrete value you don't actually "
    "have (a phone number, a file path, a name), you MUST reply in plain "
    "text asking the operator for it. Do not call a tool with a guessed, "
    "invented, or placeholder value (real-looking or not, including things "
    "like 'XXXXXXX') under any circumstances — a wrong value sent to a real "
    "tool has a real-world side effect.\n\n"
    "Once a tool result shows the request is done, stop calling tools and "
    "reply to the operator in plain text summarizing what happened. Never "
    "call the same tool with the same arguments more than once — if a tool "
    "already succeeded, it doesn't need to run again.\n\n"
    "Only ever state a tool's actual returned result — never invent, "
    "estimate, or paraphrase-into-a-different-value what a tool call "
    "returned (e.g. do not make up a time, a file's contents, or any other "
    "fact instead of using what the tool actually gave back). If a tool "
    "call errors or its result is unclear, say so honestly rather than "
    "presenting a guess as fact."
)

MAX_TURNS = 8

TOOL_SCHEMAS = [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in TOOLS]


@dataclass
class PendingConfirmation:
    confirmation_id: str
    tool_call_id: str
    tool_name: str
    arguments: dict
    summary: str


@dataclass
class AgentResult:
    kind: str  # "reply" | "confirm"
    reply: str | None = None
    confirmation: PendingConfirmation | None = None


@dataclass
class _Session:
    messages: list[dict] = field(default_factory=list)
    provider: str = "groq"
    model: str | None = None
    turns_used: int = 0
    queue: list[dict] = field(default_factory=list)


_SESSIONS: dict[str, _Session] = {}
_PENDING: dict[str, tuple[str, dict]] = {}  # confirmation_id -> (session_id, tool_call)


def _run_tool(spec, arguments: dict) -> Any:
    try:
        return spec.handler(**arguments)
    except Exception as exc:  # noqa: BLE001 - surface the error to the model, don't crash
        return {"error": str(exc)}


def _record_tool_result(session: _Session, call: dict, result: Any) -> None:
    session.messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": result})


def _process_queue(session_id: str, session: _Session) -> AgentResult:
    """Run queued tool calls in order until one needs confirmation, or the queue empties."""
    while session.queue:
        call = session.queue.pop(0)
        spec = TOOLS_BY_NAME.get(call["name"])

        if spec is None:
            _record_tool_result(session, call, {"error": f"Unknown tool '{call['name']}'"})
            continue

        if spec.validate is not None:
            try:
                spec.validate(call["arguments"])
            except Exception as exc:  # noqa: BLE001 - reject bad args before confirming or running
                _record_tool_result(session, call, {"error": str(exc)})
                continue

        if spec.safety == "confirm":
            confirmation_id = str(uuid.uuid4())
            summary = spec.summarize(call["arguments"]) if spec.summarize else f"Run {spec.name}?"
            _PENDING[confirmation_id] = (session_id, call)
            return AgentResult(
                kind="confirm",
                confirmation=PendingConfirmation(
                    confirmation_id=confirmation_id,
                    tool_call_id=call["id"],
                    tool_name=spec.name,
                    arguments=call["arguments"],
                    summary=summary,
                ),
            )

        _record_tool_result(session, call, _run_tool(spec, call["arguments"]))

    return _run_turn(session_id, session)


def _run_turn(session_id: str, session: _Session) -> AgentResult:
    if session.turns_used >= MAX_TURNS:
        return AgentResult(
            kind="reply",
            reply="I hit my step limit for this task — let me know if you'd like me to continue.",
        )

    session.turns_used += 1
    result = chat(
        messages=session.messages,
        system_prompt=SYSTEM_PROMPT,
        provider=session.provider,
        model=session.model,
        tools=TOOL_SCHEMAS,
    )

    tool_calls = result.get("tool_calls") or []
    session.messages.append({"role": "assistant", "content": result.get("content"), "tool_calls": tool_calls})

    if not tool_calls:
        return AgentResult(kind="reply", reply=result.get("content") or "")

    session.queue = list(tool_calls)
    return _process_queue(session_id, session)


def start_agent(user_message: str, provider: str = "groq", model: str | None = None) -> AgentResult:
    session_id = str(uuid.uuid4())
    session = _Session(messages=[{"role": "user", "content": user_message}], provider=provider, model=model)
    _SESSIONS[session_id] = session

    result = _run_turn(session_id, session)
    if result.kind != "confirm":
        _SESSIONS.pop(session_id, None)
    return result


def resume_agent(confirmation_id: str, approved: bool) -> AgentResult:
    pending = _PENDING.pop(confirmation_id, None)
    if pending is None:
        raise KeyError(f"No pending confirmation '{confirmation_id}'")

    session_id, call = pending
    session = _SESSIONS.get(session_id)
    if session is None:
        raise KeyError(f"Session for confirmation '{confirmation_id}' expired")

    if approved:
        spec = TOOLS_BY_NAME[call["name"]]
        result = _run_tool(spec, call["arguments"])
    else:
        result = {
            "denied": True,
            "instruction": (
                "The operator denied this action. Do not retry it or call this tool again "
                "this turn — just tell the operator you've cancelled it."
            ),
        }

    _record_tool_result(session, call, result)

    outcome = _process_queue(session_id, session)
    if outcome.kind != "confirm":
        _SESSIONS.pop(session_id, None)
    return outcome
