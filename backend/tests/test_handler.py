"""Tests for app.handler — exceptions + error responses."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.handler.exceptions import (
    MediaTranXError,
    ModelNotFoundError,
    FFmpegError,
    FileNotFoundError_,
    RemoteApiError,
    TaskCancelledError,
    ConfigError,
)
from app.handler.error_responses import register_exception_handlers


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self):
        for exc_cls in [
            ModelNotFoundError, FFmpegError, FileNotFoundError_,
            RemoteApiError, TaskCancelledError, ConfigError,
        ]:
            assert issubclass(exc_cls, MediaTranXError)

    def test_remote_api_error_to_dict(self):
        e = RemoteApiError(code="rate_limit", detail="429 Too Many Requests")
        d = e.to_dict()
        assert d["error_code"] == "rate_limit"
        assert d["detail"] == "429 Too Many Requests"

    def test_remote_api_error_str(self):
        e = RemoteApiError(code="timeout", detail="30s")
        assert "[timeout]" in str(e)


@pytest.fixture
def test_app():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-not-found")
    async def _():
        raise FileNotFoundError_("file_abc not found")

    @app.get("/raise-model-not-found")
    async def _():
        raise ModelNotFoundError("realesrgan missing")

    @app.get("/raise-ffmpeg")
    async def _():
        raise FFmpegError("encoder failed")

    @app.get("/raise-remote")
    async def _():
        raise RemoteApiError(code="auth_failed", detail="invalid key")

    @app.get("/raise-value")
    async def _():
        raise ValueError("bad input")

    @app.get("/raise-generic")
    async def _():
        raise MediaTranXError("something broke")

    return app


class TestErrorResponses:
    @pytest.mark.asyncio
    async def test_file_not_found_404(self, test_app):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            r = await c.get("/raise-not-found")
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_model_not_found_404(self, test_app):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            r = await c.get("/raise-model-not-found")
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_ffmpeg_500(self, test_app):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            r = await c.get("/raise-ffmpeg")
            assert r.status_code == 500

    @pytest.mark.asyncio
    async def test_remote_502(self, test_app):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            r = await c.get("/raise-remote")
            assert r.status_code == 502
            assert r.json()["error_code"] == "auth_failed"

    @pytest.mark.asyncio
    async def test_value_error_400(self, test_app):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            r = await c.get("/raise-value")
            assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_500(self, test_app):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            r = await c.get("/raise-generic")
            assert r.status_code == 500
