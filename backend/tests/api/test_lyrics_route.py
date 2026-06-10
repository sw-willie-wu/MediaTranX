"""Route-level tests for POST /audio/lyrics.

These tests guard against silent Pydantic field-drop: if the request model
still has old field names (whisper_size / target_lang), extra='ignore' would
silently discard the new keys and revert to defaults — this test catches that
by using non-default values and asserting they reach the service.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer


def _make_app(fake_svc):
    container = AppContainer()
    container.audio_lyrics.override(fake_svc)
    from app.api.routes.audio.lyrics import router
    app = FastAPI()
    app.include_router(router, prefix="/audio")
    container.wire(modules=["app.api.routes.audio.lyrics"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    fake.submit_lyrics = AsyncMock(return_value="task-lyrics-1")
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.audio_lyrics.reset_override()


# ---------------------------------------------------------------------------
# model_size is forwarded to service.submit_lyrics
# ---------------------------------------------------------------------------

def test_model_size_forwarded(client):
    """POST body model_size must reach submit_lyrics kwargs.

    Uses non-default value (large-v3, not 'medium') on purpose: if the request
    model still had the old field name 'whisper_size' and Pydantic extra='ignore'
    dropped the new key, the kwarg would fall back to 'medium' and the assert
    would fail.
    """
    tc, fake = client
    res = tc.post(
        "/audio/lyrics",
        json={"file_id": "f1", "model_size": "large-v3"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "task-lyrics-1"

    kwargs = fake.submit_lyrics.call_args.kwargs
    assert kwargs["model_size"] == "large-v3", (
        f"model_size not forwarded: {kwargs}"
    )


# ---------------------------------------------------------------------------
# target_language is forwarded to service.submit_lyrics
# ---------------------------------------------------------------------------

def test_target_language_forwarded(client):
    """POST body target_language must reach submit_lyrics kwargs.

    Uses non-default value (zh-TW, not None) on purpose: if the request model
    still had the old field name 'target_lang' and Pydantic extra='ignore'
    dropped the new key, the kwarg would fall back to None and the assert
    would fail.
    """
    tc, fake = client
    res = tc.post(
        "/audio/lyrics",
        json={"file_id": "f1", "translate": True, "target_language": "zh-TW"},
    )
    assert res.status_code == 200, res.text

    kwargs = fake.submit_lyrics.call_args.kwargs
    assert kwargs["target_language"] == "zh-TW", (
        f"target_language not forwarded: {kwargs}"
    )
