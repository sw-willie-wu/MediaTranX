"""AgentSessionService tests (in-memory real_db fixture)."""
import pytest

from app.services.agent.agent_session_service import AgentSessionService


@pytest.fixture
def svc(real_db):
    return AgentSessionService()


def test_append_then_list(svc):
    svc.append_message("s1", "user", content="hello")
    sessions = svc.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == "s1"
    assert sessions[0]["last_preview"] == "hello"
    assert sessions[0]["message_count"] == 1
    assert "updated_at" in sessions[0]


def test_get_messages_missing_returns_none(svc):
    assert svc.get_messages("nope") is None


def test_get_messages_maps_to_frontend_shape(svc):
    svc.append_message("s1", "user", content="hi")
    svc.append_message(
        "s1", "assistant", content="",
        tool_calls=[{"id": "c1", "function": {"name": "set_field", "arguments": "{}"}}],
    )
    svc.append_message("s1", "tool", content='{"ok":true}', tool_call_id="c1")
    svc.append_message("s1", "assistant", content="done")

    result = svc.get_messages("s1")
    assert result["id"] == "s1"
    msgs = result["messages"]
    assert msgs[0] == {"role": "user", "content": "hi"}
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["toolCalls"][0]["id"] == "c1"
    assert msgs[2] == {"role": "tool", "content": '{"ok":true}', "toolCallId": "c1"}
    assert msgs[3] == {"role": "assistant", "content": "done"}
    # assistant with no tool calls must NOT carry a toolCalls key
    assert "toolCalls" not in msgs[3]


def test_delete_session(svc):
    svc.append_message("s1", "user", content="a")
    svc.delete_session("s1")
    assert svc.get_messages("s1") is None
    assert svc.list_sessions() == []
