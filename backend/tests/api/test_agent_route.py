"""Tests for POST /api/agent/run route (Wave 1 Task 1.5)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fake_input_dict(
    text: str = "hello",
    thread_id: str = "t1",
    run_id: str = "r1",
) -> dict:
    """Build a RunAgentInput-shaped dict ready for HTTP POST body.

    Uses camelCase field aliases that the ag_ui Pydantic model serializes from:
      thread_id   → threadId
      run_id      → runId
      forwarded_props → forwardedProps
    Messages need an 'id' field (SDK requirement).
    """
    return {
        "threadId": thread_id,
        "runId": run_id,
        "messages": [{"id": "m0", "role": "user", "content": text}],
        "tools": [],
        "state": {"agent_model_choice": "qwen3:8b"},
        "context": [],
        "forwardedProps": {},
    }


def _make_app_with_fake_svc(fake_svc) -> tuple[FastAPI, AppContainer]:
    """Return (FastAPI app, container) with agent_service overridden to fake_svc.

    Builds a minimal app (no full lifespan/middleware) so tests are fast and
    isolated. The container is wired to app.api.routes.agent only.
    """
    container = AppContainer()
    container.agent_service.override(fake_svc)

    from app.api.routes.agent import router as agent_router

    app = FastAPI()
    app.include_router(agent_router, prefix="/agent")
    container.wire(modules=["app.api.routes.agent.run"])

    return app, container


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentRoute:

    def test_run_streams_events(self):
        """Mock AgentService to yield 3 fake SSE strings, verify response body."""

        async def fake_run(input, accept=None):
            yield 'event: RUN_STARTED\ndata: {"runId":"r1","threadId":"t1"}\n\n'
            yield 'event: TEXT_MESSAGE_CHUNK\ndata: {"messageId":"m1","role":"assistant","delta":"hello"}\n\n'
            yield 'event: RUN_FINISHED\ndata: {"runId":"r1","threadId":"t1"}\n\n'

        fake_svc = MagicMock()
        fake_svc.run = fake_run

        app, container = _make_app_with_fake_svc(fake_svc)
        try:
            client = TestClient(app)
            response = client.post("/agent/run", json=make_fake_input_dict())

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = response.text
            assert "RUN_STARTED" in body
            assert "TEXT_MESSAGE_CHUNK" in body
            assert "RUN_FINISHED" in body
            assert "hello" in body
        finally:
            container.unwire()
            container.agent_service.reset_override()

    def test_run_missing_required_body_fields_returns_422(self):
        """Pydantic validation rejects malformed body (missing required fields)."""
        fake_svc = MagicMock()

        async def fake_run(input, accept=None):
            yield 'event: RUN_FINISHED\ndata: {}\n\n'

        fake_svc.run = fake_run
        app, container = _make_app_with_fake_svc(fake_svc)
        try:
            client = TestClient(app)
            # Missing runId, messages, tools, state, context, forwardedProps
            response = client.post("/agent/run", json={"threadId": "t1"})
            assert response.status_code == 422
        finally:
            container.unwire()
            container.agent_service.reset_override()

    def test_run_passes_accept_header_through(self):
        """Verify route extracts request.headers['accept'] and passes to svc.run()."""
        captured_accept: list[str | None] = []

        async def fake_run(input, accept=None):
            captured_accept.append(accept)
            yield 'event: RUN_FINISHED\ndata: {}\n\n'

        fake_svc = MagicMock()
        fake_svc.run = fake_run
        app, container = _make_app_with_fake_svc(fake_svc)
        try:
            client = TestClient(app)
            response = client.post(
                "/agent/run",
                json=make_fake_input_dict(),
                headers={"accept": "text/event-stream"},
            )
            assert response.status_code == 200
            assert captured_accept == ["text/event-stream"]
        finally:
            container.unwire()
            container.agent_service.reset_override()

    def test_run_sets_no_cache_headers(self):
        """Verify Cache-Control: no-cache and X-Accel-Buffering: no are set."""

        async def fake_run(input, accept=None):
            yield 'event: RUN_FINISHED\ndata: {}\n\n'

        fake_svc = MagicMock()
        fake_svc.run = fake_run
        app, container = _make_app_with_fake_svc(fake_svc)
        try:
            client = TestClient(app)
            response = client.post("/agent/run", json=make_fake_input_dict())
            assert response.headers.get("cache-control") == "no-cache"
            assert response.headers.get("x-accel-buffering") == "no"
        finally:
            container.unwire()
            container.agent_service.reset_override()

    def test_run_empty_tools_accepted(self):
        """Verify that an empty tools list is accepted (common real-world case)."""
        received_tools: list = []

        async def fake_run(input, accept=None):
            received_tools.extend(input.tools)
            yield 'event: RUN_FINISHED\ndata: {}\n\n'

        fake_svc = MagicMock()
        fake_svc.run = fake_run
        app, container = _make_app_with_fake_svc(fake_svc)
        try:
            client = TestClient(app)
            body = make_fake_input_dict()
            body["tools"] = []
            response = client.post("/agent/run", json=body)
            assert response.status_code == 200
            assert received_tools == []
        finally:
            container.unwire()
            container.agent_service.reset_override()
