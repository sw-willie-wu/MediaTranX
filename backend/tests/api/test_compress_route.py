"""Route-level tests for POST /image/compress."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer


def _make_app(fake_compress_svc):
    container = AppContainer()
    container.image_compress.override(fake_compress_svc)
    from app.api.routes.image.compress import router
    app = FastAPI()
    app.include_router(router, prefix="/image")
    container.wire(modules=["app.api.routes.image.compress"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    fake.submit_compress = AsyncMock(return_value="task-compress-1")
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.image_compress.reset_override()


def test_compress_route_returns_task_id(client):
    """POST /image/compress must return a task_id (not 404)."""
    tc, fake = client
    res = tc.post("/image/compress", json={"file_id": "f1"})
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "task-compress-1"


def test_compress_route_forwards_strength(client):
    """Non-default strength is forwarded to submit_compress."""
    tc, fake = client
    res = tc.post("/image/compress", json={"file_id": "f2", "strength": 30})
    assert res.status_code == 200, res.text
    call_kwargs = fake.submit_compress.call_args.kwargs
    assert call_kwargs["file_id"] == "f2"
    assert call_kwargs["strength"] == 30


def test_compress_route_defaults(client):
    """When only file_id is given, defaults (strength=60) apply."""
    tc, fake = client
    res = tc.post("/image/compress", json={"file_id": "f3"})
    assert res.status_code == 200, res.text
    call_kwargs = fake.submit_compress.call_args.kwargs
    assert call_kwargs["strength"] == 60


def test_compress_route_forwards_gif_opts(client):
    """GIF-specific opts are forwarded through **opts."""
    tc, fake = client
    res = tc.post(
        "/image/compress",
        json={
            "file_id": "f4",
            "strength": 80,
            "gif_colors": 128,
            "gif_frame_drop": 2,
            "gif_optimize_transparency": False,
        },
    )
    assert res.status_code == 200, res.text
    call_kwargs = fake.submit_compress.call_args.kwargs
    assert call_kwargs["gif_colors"] == 128
    assert call_kwargs["gif_frame_drop"] == 2
    assert call_kwargs["gif_optimize_transparency"] is False
