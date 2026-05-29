"""AgentSessionDAO tests (use the in-memory real_db fixture)."""
import pytest

from app.db.dao.agent_session_dao import AgentSessionDAO


@pytest.fixture
def dao(real_db):
    return AgentSessionDAO()


def test_append_lazily_creates_session(dao):
    dao.append_message("s1", "user", "hello", None, None, "2026-05-29T00:00:00+00:00")
    sess = dao.get_session("s1")
    assert sess is not None
    assert sess.id == "s1"
    assert sess.message_count == 1
    assert sess.last_preview == "hello"
    assert sess.created_at == "2026-05-29T00:00:00+00:00"
    assert sess.updated_at == "2026-05-29T00:00:00+00:00"


def test_get_session_missing_returns_none(dao):
    assert dao.get_session("nope") is None


def test_seq_is_monotonic_and_count_bumps(dao):
    dao.append_message("s1", "user", "a", None, None, "2026-05-29T00:00:00+00:00")
    dao.append_message("s1", "assistant", "b", None, None, "2026-05-29T00:00:01+00:00")
    dao.append_message("s1", "tool", "{}", None, "call_1", "2026-05-29T00:00:02+00:00")
    rows = dao.get_messages("s1")
    assert [r.seq for r in rows] == [0, 1, 2]
    assert [r.role for r in rows] == ["user", "assistant", "tool"]
    sess = dao.get_session("s1")
    assert sess.message_count == 3
    assert sess.last_preview == "{}"
    assert sess.updated_at == "2026-05-29T00:00:02+00:00"


def test_get_messages_ordered_by_seq(dao):
    for i in range(5):
        dao.append_message("s1", "user", f"m{i}", None, None, f"2026-05-29T00:00:0{i}+00:00")
    rows = dao.get_messages("s1")
    assert [r.content for r in rows] == ["m0", "m1", "m2", "m3", "m4"]


def test_tool_calls_and_tool_call_id_stored(dao):
    dao.append_message("s1", "assistant", "", '[{"id":"c1"}]', None, "2026-05-29T00:00:00+00:00")
    dao.append_message("s1", "tool", "result", None, "c1", "2026-05-29T00:00:01+00:00")
    rows = dao.get_messages("s1")
    assert rows[0].tool_calls == '[{"id":"c1"}]'
    assert rows[0].tool_call_id is None
    assert rows[1].tool_call_id == "c1"
    assert rows[1].tool_calls is None


def test_list_sessions_ordered_by_updated_desc(dao):
    dao.append_message("s1", "user", "first", None, None, "2026-05-29T00:00:00+00:00")
    dao.append_message("s2", "user", "second", None, None, "2026-05-29T00:00:05+00:00")
    sessions = dao.list_sessions()
    assert [s.id for s in sessions] == ["s2", "s1"]


def test_delete_session_cascades_messages(dao):
    dao.append_message("s1", "user", "a", None, None, "2026-05-29T00:00:00+00:00")
    dao.append_message("s1", "assistant", "b", None, None, "2026-05-29T00:00:01+00:00")
    assert dao.delete_session("s1") is True
    assert dao.get_session("s1") is None
    assert dao.get_messages("s1") == []


def test_delete_missing_session_returns_false(dao):
    assert dao.delete_session("nope") is False
