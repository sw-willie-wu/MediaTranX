import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.configs import Settings
from backend.api.middleware import RequestHandlingMiddleware
from backend.api.routes import api_router


LOGGER = logging.getLogger(__name__)


def build_router(app: FastAPI, settings: Settings = Settings()) -> FastAPI:
    # CORS 設定
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8000", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Gzip 壓縮
    app.add_middleware(GZipMiddleware, minimum_size=1024 * 1024)

    # 包含 API 路由
    app.include_router(api_router, prefix="/api")

    # 掛載靜態檔案（Vue 前端）
    app.mount(
        "/static",
        StaticFiles(
            directory=settings.UI.StaticFiles,
            html=True
        ),
        name="vue-frontend"
    )

    LOGGER.info("API routes configured")
    return app
