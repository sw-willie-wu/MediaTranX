"""Tests for /api/agent/sessions routes."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer


def _make_app(fake_svc) -> tuple[FastAPI, AppContainer]:
    container = AppContainer()
    container.agent_session_service.override(fake_svc)

    from app.api.routes.agent import router as agent_router

    app = FastAPI()
    app.include_router(agent_router, prefix="/agent")
    container.wire(modules=["app.api.routes.agent.sessions"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.agent_session_service.reset_override()


def test_list_sessions(client):
    tc, fake = client
    fake.list_sessions.return_value = [
        {"id": "s2", "last_preview": "hi", "updated_at": "2026-05-29T00:00:05+00:00", "message_count": 2},
    ]
    res = tc.get("/agent/sessions")
    assert res.status_code == 200
    assert res.json()[0]["id"] == "s2"
    fake.list_sessions.assert_called_once()


def test_get_messages_ok(client):
    tc, fake = client
    fake.get_messages.return_value = {"id": "s1", "messages": [{"role": "user", "content": "hi"}]}
    res = tc.get("/agent/sessions/s1/messages")
    assert res.status_code == 200
    assert res.json()["messages"][0]["content"] == "hi"
    fake.get_messages.assert_called_once_with("s1")


def test_get_messages_404(client):
    tc, fake = client
    fake.get_messages.return_value = None
    res = tc.get("/agent/sessions/nope/messages")
    assert res.status_code == 404


def test_append_message_lazy_create(client):
    tc, fake = client
    body = {
        "role": "assistant",
        "content": "done",
        "tool_calls": [{"id": "c1", "function": {"name": "set_field", "arguments": "{}"}}],
    }
    res = tc.post("/agent/sessions/s1/messages", json=body)
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    fake.append_message.assert_called_once_with(
        session_id="s1",
        role="assistant",
        content="done",
        tool_calls=[{"id": "c1", "function": {"name": "set_field", "arguments": "{}"}}],
        tool_call_id=None,
    )


def test_delete_session_idempotent(client):
    tc, fake = client
    res = tc.delete("/agent/sessions/s1")
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    fake.delete_session.assert_called_once_with("s1")
