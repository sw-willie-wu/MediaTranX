"""Tests for GET /setup/config/compute and PUT /setup/config/compute routes."""
from __future__ import annotations
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer
from app.schemas.compute_settings import ComputeSettings


def _make_app(fake_svc):
    container = AppContainer()
    container.compute_settings_service.override(fake_svc)
    from app.api.routes.setup.config import router as config_router
    app = FastAPI()
    app.include_router(config_router, prefix="/setup")   # config route 含 "/config/compute"
    container.wire(modules=["app.api.routes.setup.config"])
    return app, container


@pytest.fixture
def client():
    fake = MagicMock()
    app, container = _make_app(fake)
    try:
        yield TestClient(app), fake
    finally:
        container.unwire()
        container.compute_settings_service.reset_override()


def test_get_compute_settings(client):
    tc, fake = client
    fake.get_settings.return_value = ComputeSettings(allow_cpu_fallback=False)
    res = tc.get("/setup/config/compute")
    assert res.status_code == 200
    assert res.json()["allow_cpu_fallback"] is False


def test_put_compute_settings(client):
    tc, fake = client
    fake.update_settings.return_value = ComputeSettings(allow_cpu_fallback=False)
    res = tc.put("/setup/config/compute", json={"allow_cpu_fallback": False})
    assert res.status_code == 200
    assert res.json()["allow_cpu_fallback"] is False
    fake.update_settings.assert_called_once_with({"allow_cpu_fallback": False})
