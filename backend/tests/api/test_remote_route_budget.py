"""Tests for chunk_ctx_budget in remote connection routes.

Verifies:
- POST /api/setup/remote/connections accepts chunk_ctx_budget and persists it.
- PUT /api/setup/remote/connections/{id} with explicit null resets the field
  (the exclude_unset=True fix — exclude_none=True would silently drop the null).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer
from app.services.setup.remote_service import RemoteService


@pytest.fixture
def client(real_db):
    from app.api.routes.setup.remote import router as remote_router

    app = FastAPI()
    app.include_router(remote_router, prefix="/api/setup")
    container = AppContainer()
    container.remote_service.override(RemoteService())   # real service over real_db
    container.wire(packages=["app.api.routes.setup"])
    try:
        yield TestClient(app)
    finally:
        container.unwire()
        container.remote_service.reset_override()


def test_create_with_budget(client):
    """POST with chunk_ctx_budget persists the value."""
    r = client.post(
        "/api/setup/remote/connections",
        json={"provider": "ollama", "name": "x", "endpoint": "http://h",
              "chunk_ctx_budget": 20000},
    )
    assert r.status_code == 200, r.text
    assert r.json()["chunk_ctx_budget"] == 20000


def test_create_and_reset_budget(client):
    """Create with a budget, then reset to auto via explicit null."""
    r = client.post(
        "/api/setup/remote/connections",
        json={"provider": "ollama", "name": "x", "endpoint": "http://h",
              "chunk_ctx_budget": 20000},
    )
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert r.json()["chunk_ctx_budget"] == 20000

    # reset to auto: explicit null must actually clear the value
    r2 = client.put(
        f"/api/setup/remote/connections/{cid}",
        json={"chunk_ctx_budget": None},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["chunk_ctx_budget"] is None


def test_update_other_field_does_not_clear_budget(client):
    """Updating an unrelated field leaves chunk_ctx_budget untouched."""
    r = client.post(
        "/api/setup/remote/connections",
        json={"provider": "ollama", "name": "y", "endpoint": "http://h2",
              "chunk_ctx_budget": 8192},
    )
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    r2 = client.put(
        f"/api/setup/remote/connections/{cid}",
        json={"name": "y-renamed"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["chunk_ctx_budget"] == 8192


@pytest.mark.parametrize("bad", [100, 1024, 999999999])
def test_create_rejects_out_of_range_budget(client, bad):
    """Out-of-range chunk_ctx_budget is rejected by schema validation (not stored)."""
    r = client.post(
        "/api/setup/remote/connections",
        json={"provider": "ollama", "name": "z", "endpoint": "http://h",
              "chunk_ctx_budget": bad},
    )
    assert r.status_code == 422, r.text
