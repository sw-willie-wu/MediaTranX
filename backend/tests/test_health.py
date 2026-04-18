"""Tests for health check endpoints."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def health_app():
    """Minimal app with just health routes + exception handlers."""
    from unittest.mock import MagicMock, patch

    mock_container = MagicMock()
    mock_device = MagicMock()
    mock_device.get_device_info.return_value = {"gpu": "none"}
    mock_container.device_service.return_value = mock_device

    mock_tm = MagicMock()
    mock_tm.get_active_tasks.return_value = []
    mock_container.task_manager.return_value = mock_tm

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn

    with patch("app.api.routes.health.health.get_container", return_value=mock_container), \
         patch("app.db.database.get_engine", return_value=mock_engine):
        from app.api.routes.health import router
        app = FastAPI()
        app.include_router(router)
        yield app


class TestHealthCheck:
    async def test_shallow_health(self, health_app):
        async with AsyncClient(transport=ASGITransport(app=health_app), base_url="http://test") as c:
            r = await c.get("/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

    async def test_deep_health_ok(self, health_app):
        async with AsyncClient(transport=ASGITransport(app=health_app), base_url="http://test") as c:
            r = await c.get("/health/deep")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "ok"
            assert "db" in data["checks"]
            assert "task_manager" in data["checks"]
