"""
The confirm gate is the one piece of NEXUS that must never fail quietly:
a "confirm" tool (whatsapp_send, write_file, delete_file) may only ever
run after an explicit approve, and a deny must genuinely do nothing. The
LLM itself is stubbed out here — these tests exercise the agent loop's
own bookkeeping, not Groq, and never touch the real whatsapp_send handler.
"""
import dataclasses
from unittest.mock import Mock

import pytest

import app.agent as agent_module
from app.agent import resume_agent, start_agent
from app.tools.registry import TOOLS_BY_NAME

TOOL_CALL_RESPONSE = {
    "content": None,
    "tool_calls": [
        {"id": "call-1", "name": "whatsapp_send", "arguments": {"phone": "9999999999", "message": "hi"}}
    ],
}


@pytest.fixture
def fake_whatsapp_handler(monkeypatch):
    handler = Mock(return_value={"sent_to": "9999999999", "verified": True})
    monkeypatch.setitem(
        TOOLS_BY_NAME,
        "whatsapp_send",
        dataclasses.replace(TOOLS_BY_NAME["whatsapp_send"], handler=handler),
    )
    return handler


def _stub_chat(monkeypatch, *responses):
    monkeypatch.setattr(agent_module, "chat", Mock(side_effect=list(responses)))


def test_agent_pauses_for_confirmation_before_touching_the_tool(monkeypatch, fake_whatsapp_handler):
    _stub_chat(monkeypatch, TOOL_CALL_RESPONSE)

    result = start_agent("send hi to 9999999999 on whatsapp")

    assert result.kind == "confirm"
    assert result.confirmation.tool_name == "whatsapp_send"
    fake_whatsapp_handler.assert_not_called()


def test_deny_never_calls_the_handler(monkeypatch, fake_whatsapp_handler):
    _stub_chat(monkeypatch, TOOL_CALL_RESPONSE, {"content": "Okay, cancelled.", "tool_calls": []})

    result = start_agent("send hi to 9999999999 on whatsapp")
    outcome = resume_agent(result.confirmation.confirmation_id, approved=False)

    assert outcome.kind == "reply"
    fake_whatsapp_handler.assert_not_called()


def test_approve_calls_the_handler_exactly_once_with_the_confirmed_arguments(monkeypatch, fake_whatsapp_handler):
    _stub_chat(monkeypatch, TOOL_CALL_RESPONSE, {"content": "Sent.", "tool_calls": []})

    result = start_agent("send hi to 9999999999 on whatsapp")
    resume_agent(result.confirmation.confirmation_id, approved=True)

    fake_whatsapp_handler.assert_called_once_with(phone="9999999999", message="hi")


def test_a_confirmation_cannot_be_resolved_twice(monkeypatch, fake_whatsapp_handler):
    _stub_chat(monkeypatch, TOOL_CALL_RESPONSE, {"content": "Okay, cancelled.", "tool_calls": []})

    result = start_agent("send hi to 9999999999 on whatsapp")
    confirmation_id = result.confirmation.confirmation_id
    resume_agent(confirmation_id, approved=False)

    with pytest.raises(KeyError):
        resume_agent(confirmation_id, approved=True)
    fake_whatsapp_handler.assert_not_called()
