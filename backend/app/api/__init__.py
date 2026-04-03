import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes import api_router
from app.handler.middleware import RequestLifecycleMiddleware
from app.init.configs import get_settings


LOGGER = logging.getLogger(__name__)


def build_router(app: FastAPI) -> FastAPI:
    # CORS 設定：dev 允許所有 origin，prod 僅允許 file:// (null)
    if get_settings().is_frozen:
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

    # Request lifecycle (session ID + timing)
    app.add_middleware(RequestLifecycleMiddleware)

    # 包含 API 路由
    app.include_router(api_router, prefix="/api")

    LOGGER.info("API routes configured")
    return app
