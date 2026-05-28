import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.init.container import AppContainer


@pytest.fixture
def client():
    container = AppContainer()
    svc = MagicMock()
    svc.reveal_key.return_value = "sk-REVEALED"
    container.remote_service.override(svc)

    from app.api.routes.setup.remote import router as remote_router

    app = FastAPI()
    app.include_router(remote_router, prefix="/api/setup")   # router paths start /remote/...
    container.wire(packages=["app.api.routes.setup"])
    try:
        yield TestClient(app), svc
    finally:
        container.unwire()
        container.remote_service.reset_override()


def test_reveal_returns_key_in_body_with_no_store(client):
    tc, svc = client
    res = tc.post("/api/setup/remote/connections/7/key")
    assert res.status_code == 200
    assert res.json() == {"api_key": "sk-REVEALED"}
    assert res.headers["cache-control"] == "no-store"   # httpx headers are case-insensitive
    svc.reveal_key.assert_called_once_with(7)
