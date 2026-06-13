"""Route-level tests for POST /audio/transcribe.

These tests guard against silent Pydantic field-drop: if the request model
still has old field names (language / target_lang), extra='ignore' would
silently discard the new keys and revert to defaults (None) — this test
catches that by using non-default values and asserting they reach the service.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer


def _make_app(fake_svc):
    container = AppContainer()
    container.audio_transcribe.override(fake_svc)
    from app.api.routes.audio.transcribe import router
    app = FastAPI()
    app.include_router(router, prefix="/audio")
    container.wire(modules=["app.api.routes.audio.transcribe"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    fake.submit_transcribe = AsyncMock(return_value="task-transcribe-1")
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.audio_transcribe.reset_override()


# ---------------------------------------------------------------------------
# source_language is forwarded to service.submit_transcribe
# ---------------------------------------------------------------------------

def test_source_language_forwarded(client):
    """POST body source_language must reach submit_transcribe kwargs.

    Uses non-default value (ja, not None) on purpose: if the request model
    still had the old field name 'language' and Pydantic extra='ignore' dropped
    the new key, the kwarg would fall back to None and the assert would fail.
    """
    tc, fake = client
    res = tc.post(
        "/audio/transcribe",
        json={"file_id": "f1", "source_language": "ja"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "task-transcribe-1"

    kwargs = fake.submit_transcribe.call_args.kwargs
    assert kwargs["source_language"] == "ja", (
        f"source_language not forwarded: {kwargs}"
    )


# ---------------------------------------------------------------------------
# target_language is forwarded to service.submit_transcribe
# ---------------------------------------------------------------------------

def test_target_language_forwarded(client):
    """POST body target_language must reach submit_transcribe kwargs.

    Uses non-default value (zh-TW, not None) on purpose: if the request model
    still had the old field name 'target_lang' and Pydantic extra='ignore'
    dropped the new key, the kwarg would fall back to None and the assert
    would fail.
    """
    tc, fake = client
    res = tc.post(
        "/audio/transcribe",
        json={"file_id": "f1", "translate": True, "target_language": "zh-TW"},
    )
    assert res.status_code == 200, res.text

    kwargs = fake.submit_transcribe.call_args.kwargs
    assert kwargs["target_language"] == "zh-TW", (
        f"target_language not forwarded: {kwargs}"
    )
