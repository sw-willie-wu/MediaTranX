import sys
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes import api_router


LOGGER = logging.getLogger(__name__)

_IS_FROZEN = getattr(sys, 'frozen', False) or "__compiled__" in globals()


def build_router(app: FastAPI) -> FastAPI:
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

    # 初始化資料庫（SQLModel 建表）
    @app.on_event("startup")
    async def _init_database():
        from app.db import init_db
        init_db()

    # 任務歷史紀錄：監聽任務終態並寫入 SQLite
    @app.on_event("startup")
    async def _register_task_history_hook():
        from app.workers.task_manager import get_task_manager
        from app.services.tasks import get_task_history_service

        history = get_task_history_service()
        tm = get_task_manager()

        def _on_terminal(task):
            try:
                result = task.result if isinstance(task.result, dict) else None
                history.save(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    status=task.status.value,
                    created_at=task.created_at,
                    completed_at=task.updated_at,
                    label=task.label,
                    error=task.error,
                    error_code=task.error_code,
                    result=result,
                )
            except Exception as e:
                LOGGER.warning(f"Failed to save task history: {e}")

        tm.on_terminal(_on_terminal)
        LOGGER.info("Task history hook registered")

    LOGGER.info("API routes configured")
    return app
