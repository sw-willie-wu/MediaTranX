"""Route-level tests for POST /image/ocr.

These tests guard against silent Pydantic field-drop: if the request model
still has old field names (size / format), extra='ignore' would silently
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
    container.image_ocr.override(fake_ocr_svc)
    from app.api.routes.image.ocr import router
    app = FastAPI()
    app.include_router(router, prefix="/image")
    container.wire(modules=["app.api.routes.image.ocr"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    fake.submit_ocr = AsyncMock(return_value="task-local-1")
    fake.submit_ocr_remote = AsyncMock(return_value="task-remote-1")
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.image_ocr.reset_override()


# ---------------------------------------------------------------------------
# Local path: new field names are forwarded to service.submit_ocr
# ---------------------------------------------------------------------------

def test_local_ocr_forwards_model_size_and_output_format(client):
    """POST body model_size / output_format must reach submit_ocr kwargs.

    Uses NON-default values (8b / txt) on purpose: if the request model still
    had old field names and Pydantic extra='ignore' dropped the new keys, the
    kwargs would fall back to defaults (4b / md) and these asserts would fail.
    """
    tc, fake = client
    res = tc.post(
        "/image/ocr",
        json={
            "file_id": "f1",
            "model_size": "8b",
            "output_format": "txt",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "task-local-1"

    kwargs = fake.submit_ocr.call_args.kwargs
    assert kwargs["model_size"] == "8b", f"model_size not forwarded: {kwargs}"
    assert kwargs["output_format"] == "txt", f"output_format not forwarded: {kwargs}"


def test_local_ocr_defaults_applied_when_omitted(client):
    """When model_size / output_format are absent, defaults (4b / md) are used."""
    tc, fake = client
    res = tc.post("/image/ocr", json={"file_id": "f3"})
    assert res.status_code == 200, res.text
    kwargs = fake.submit_ocr.call_args.kwargs
    assert kwargs["model_size"] == "4b"
    assert kwargs["output_format"] == "md"


# ---------------------------------------------------------------------------
# Remote path: new field name output_format is forwarded to submit_ocr_remote
# ---------------------------------------------------------------------------

def test_remote_ocr_forwards_output_format(client):
    """Remote path must forward output_format to submit_ocr_remote."""
    tc, fake = client
    res = tc.post(
        "/image/ocr",
        json={
            "file_id": "f4",
            "remote": True,
            "provider": "openai",
            "conn_id": 1,
            "remote_model": "gpt-4o",
            "output_format": "txt",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "task-remote-1"

    kwargs = fake.submit_ocr_remote.call_args.kwargs
    assert kwargs["output_format"] == "txt", f"output_format not forwarded to remote: {kwargs}"
