"""Tests for GET /setup/config/ollama and PUT /setup/config/ollama routes."""
from __future__ import annotations
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer
from app.schemas.ollama_settings import OllamaSettings


def _make_app(fake_svc):
    container = AppContainer()
    container.ollama_settings_service.override(fake_svc)
    from app.api.routes.setup.config import router as config_router
    app = FastAPI()
    app.include_router(config_router, prefix="/setup")
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
        container.ollama_settings_service.reset_override()


def test_get_ollama_settings(client):
    tc, fake = client
    fake.get_settings.return_value = OllamaSettings(ollama_num_ctx_cap=16384)
    res = tc.get("/setup/config/ollama")
    assert res.status_code == 200
    assert res.json()["ollama_num_ctx_cap"] == 16384


def test_put_ollama_settings(client):
    tc, fake = client
    fake.update_settings.return_value = OllamaSettings(ollama_num_ctx_cap=32768)
    res = tc.put("/setup/config/ollama", json={"ollama_num_ctx_cap": 32768})
    assert res.status_code == 200
    assert res.json()["ollama_num_ctx_cap"] == 32768
    fake.update_settings.assert_called_once_with({"ollama_num_ctx_cap": 32768})


def test_put_ollama_settings_rejects_out_of_bounds(client):
    tc, fake = client
    res = tc.put("/setup/config/ollama", json={"ollama_num_ctx_cap": 100})
    assert res.status_code == 422  # pydantic Field ge=4096 rejects before service
