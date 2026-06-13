"""Route-level tests for POST /document/ocr.

These tests guard against silent Pydantic field-drop: if the request model
still had old field names (size / format), extra='ignore' would silently
discard the new keys and revert to defaults — this test catches that.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer


def _make_app(fake_ocr_svc):
    container = AppContainer()
    container.doc_ocr.override(fake_ocr_svc)
    from app.api.routes.document.ocr import router
    app = FastAPI()
    app.include_router(router, prefix="/document")
    container.wire(modules=["app.api.routes.document.ocr"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    fake.submit = AsyncMock(return_value="task-local-1")
    fake.submit_remote = AsyncMock(return_value="task-remote-1")
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.doc_ocr.reset_override()


# ---------------------------------------------------------------------------
# Local path: new field names are forwarded to service.submit
# ---------------------------------------------------------------------------

def test_local_ocr_forwards_model_size_and_output_format(client):
    """POST body model_size / output_format must reach submit kwargs.

    Uses NON-default values (8b / txt) on purpose: if the request model still
    had old field names and Pydantic extra='ignore' dropped the new keys, the
    kwargs would fall back to defaults (4b / md) and these asserts would fail.

    model_family is provided so language_service.get_default_vlm_model()
    is never called, keeping this test dependency-free.
    """
    tc, fake = client
    res = tc.post(
        "/document/ocr",
        json={
            "file_id": "f1",
            "model_family": "qwen3vl",
            "model_size": "8b",
            "output_format": "txt",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "task-local-1"

    kwargs = fake.submit.call_args.kwargs
    assert kwargs["model_size"] == "8b", f"model_size not forwarded: {kwargs}"
    assert kwargs["output_format"] == "txt", f"output_format not forwarded: {kwargs}"


def test_local_ocr_defaults_applied_when_omitted(client):
    """When model_size / output_format are absent, defaults (4b / md) are used."""
    tc, fake = client
    res = tc.post(
        "/document/ocr",
        json={"file_id": "f2", "model_family": "qwen3vl"},
    )
    assert res.status_code == 200, res.text
    kwargs = fake.submit.call_args.kwargs
    assert kwargs["model_size"] == "4b"
    assert kwargs["output_format"] == "md"


# ---------------------------------------------------------------------------
# Remote path: new field name output_format is forwarded to submit_remote
# ---------------------------------------------------------------------------

def test_remote_ocr_forwards_output_format(client):
    """Remote path must forward output_format to submit_remote.

    Uses NON-default value (txt) so a silent field-drop to default (md)
    would be caught.
    """
    tc, fake = client
    res = tc.post(
        "/document/ocr",
        json={
            "file_id": "f3",
            "remote": True,
            "provider": "openai",
            "conn_id": 1,
            "remote_model": "gpt-4o",
            "output_format": "txt",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "task-remote-1"

    kwargs = fake.submit_remote.call_args.kwargs
    assert kwargs["output_format"] == "txt", f"output_format not forwarded to remote: {kwargs}"
