"""Tests for /api/video/download routes (probe / download / settings + 403 gate)."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer
from app.schemas.video_download import ProbeResponse, VideoDownloadSettings


def _make_app(fake_svc):
    container = AppContainer()
    container.video_download.override(fake_svc)
    from app.api.routes.video.download import router as download_router
    app = FastAPI()
    app.include_router(download_router, prefix="/video")
    container.wire(modules=["app.api.routes.video.download"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.video_download.reset_override()


def test_probe_403_when_disabled(client):
    tc, fake = client
    fake.is_enabled.return_value = False
    res = tc.post("/video/download/probe", json={"url": "http://x"})
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "feature_disabled"


def test_probe_ok_when_enabled(client):
    tc, fake = client
    fake.is_enabled.return_value = True
    fake.probe.return_value = ProbeResponse(downloadable=True, title="T", duration=5.0)
    res = tc.post("/video/download/probe", json={"url": "http://x"})
    assert res.status_code == 200
    assert res.json()["title"] == "T"
    fake.probe.assert_called_once_with("http://x")


def test_download_403_when_disabled(client):
    tc, fake = client
    fake.is_enabled.return_value = False
    res = tc.post("/video/download", json={"url": "http://x"})
    assert res.status_code == 403


def test_download_ok_returns_task_id(client):
    tc, fake = client
    fake.is_enabled.return_value = True
    fake.submit_download = AsyncMock(return_value="tid-123")
    res = tc.post("/video/download", json={
        "url": "http://x", "title": "Clip",
        "format_intent": {"mode": "cap", "max_height": 720},
    })
    assert res.status_code == 200
    assert res.json()["task_id"] == "tid-123"
    args, _ = fake.submit_download.call_args
    assert args[0] == "http://x"
    assert args[1].mode == "cap" and args[1].max_height == 720
    assert args[2] == "Clip"


def test_get_settings(client):
    tc, fake = client
    fake.get_settings.return_value = VideoDownloadSettings(agreed=True, enabled=True)
    res = tc.get("/video/download/settings")
    assert res.status_code == 200
    assert res.json()["enabled"] is True


def test_put_settings_passes_exclude_none_patch(client):
    tc, fake = client
    fake.update_settings.return_value = VideoDownloadSettings(agreed=True, enabled=True)
    res = tc.put("/video/download/settings", json={"agreed": True, "enabled": True})
    assert res.status_code == 200
    fake.update_settings.assert_called_once_with({"agreed": True, "enabled": True})
