"""Route-level tests for POST /video/subtitle/generate.

These tests guard against silent Pydantic field-drop: if the request model
still has the old field name 'language', extra='ignore' would silently discard
the new key and revert to default (None = auto-detect) — this test catches
that by using a non-default value and asserting it reaches the service.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer


def _make_app(fake_svc):
    container = AppContainer()
    container.video_subtitle.override(fake_svc)
    from app.api.routes.video.subtitle import router
    app = FastAPI()
    app.include_router(router, prefix="/video")
    container.wire(modules=["app.api.routes.video.subtitle"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    fake.submit_subtitle_generate = AsyncMock(return_value="task-subtitle-1")
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.video_subtitle.reset_override()


# ---------------------------------------------------------------------------
# source_language is forwarded to service.submit_subtitle_generate
# ---------------------------------------------------------------------------

def test_source_language_forwarded(client):
    """POST body source_language must reach submit_subtitle_generate kwargs.

    Uses non-default value (ja, not None) on purpose: if the request model
    still had the old field name 'language' and Pydantic extra='ignore' dropped
    the new key, the kwarg would fall back to None and the assert would fail.
    """
    tc, fake = client
    res = tc.post(
        "/video/subtitle/generate",
        json={"file_id": "f1", "source_language": "ja"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "task-subtitle-1"

    kwargs = fake.submit_subtitle_generate.call_args.kwargs
    assert kwargs["source_language"] == "ja", (
        f"source_language not forwarded: {kwargs}"
    )
