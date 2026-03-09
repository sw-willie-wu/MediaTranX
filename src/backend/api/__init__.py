import sys
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.configs import Settings
from backend.api.middleware import RequestHandlingMiddleware
from backend.api.routes import api_router


LOGGER = logging.getLogger(__name__)

_IS_FROZEN = getattr(sys, 'frozen', False) or "__compiled__" in globals()


def build_router(app: FastAPI, settings: Settings = Settings()) -> FastAPI:
    # CORS 設定：dev 允許所有 origin，prod 僅允許 file:// (null)
    if _IS_FROZEN:
        _cors_origins = ["null"]
        _cors_credentials = True
    else:
        _cors_origins = ["*"]
        _cors_credentials = False  # allow_origins=* 不能與 credentials=True 共用

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_cors_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Gzip 壓縮
    app.add_middleware(GZipMiddleware, minimum_size=1024 * 1024)

    # 包含 API 路由
    app.include_router(api_router, prefix="/api")

    # 掛載靜態檔案（Vue 前端）— 僅在 static 目錄存在時掛載
    static_dir = settings.UI.StaticFiles
    if static_dir.exists():
        app.mount(
            "/",
            StaticFiles(
                directory=static_dir,
                html=True
            ),
            name="vue-frontend"
        )
        LOGGER.info(f"Static files mounted at / from {static_dir}")
    else:
        LOGGER.warning(f"Static directory not found: {static_dir}, skipping mount")

    LOGGER.info("API routes configured")
    return app
