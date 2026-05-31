import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.init.container import AppContainer


@pytest.fixture
def client():
    container = AppContainer()
    svc = MagicMock()
    svc.list_remote_models_by_conn.return_value = [
        {"id": "m1", "name": "Model One", "capabilities": ["text"]},
    ]
    svc.test_connection.return_value = {"connected": True, "models": []}
    container.remote_service.override(svc)

    from app.api.routes.setup.remote import router as remote_router

    app = FastAPI()
    app.include_router(remote_router, prefix="/api/setup")
    container.wire(packages=["app.api.routes.setup"])
    try:
        yield TestClient(app), svc
    finally:
        container.unwire()
        container.remote_service.reset_override()


def test_list_remote_models_returns_models(client):
    tc, svc = client
    res = tc.get("/api/setup/remote/models", params={"conn_id": 4})
    assert res.status_code == 200
    assert res.json() == {"models": [{"id": "m1", "name": "Model One", "capabilities": ["text"]}]}
    svc.list_remote_models_by_conn.assert_called_once_with(4)


def test_test_connection_returns_result(client):
    tc, svc = client
    res = tc.post("/api/setup/remote/test", json={"provider": "ollama", "endpoint": "http://x"})
    assert res.status_code == 200
    assert res.json() == {"connected": True, "models": []}
    svc.test_connection.assert_called_once_with("ollama", "http://x", None)


def test_list_remote_models_returns_502_when_provider_down():
    """A down/unreachable provider → list_models raises RemoteApiError →
    route returns HTTP 502 {error_code, detail} (not 200 {models:[]})."""
    from app.handler.exceptions import RemoteApiError
    from app.handler.error_responses import register_exception_handlers
    from app.api.routes.setup.remote import router as remote_router

    container = AppContainer()
    svc = MagicMock()
    svc.list_remote_models_by_conn.side_effect = RemoteApiError("connection_failed", "down")
    container.remote_service.override(svc)

    app = FastAPI()
    register_exception_handlers(app)  # wire RemoteApiError -> 502
    app.include_router(remote_router, prefix="/api/setup")
    container.wire(packages=["app.api.routes.setup"])
    try:
        tc = TestClient(app)
        res = tc.get("/api/setup/remote/models", params={"conn_id": 1})
        assert res.status_code == 502
        assert res.json()["error_code"] == "connection_failed"
    finally:
        container.unwire()
        container.remote_service.reset_override()
