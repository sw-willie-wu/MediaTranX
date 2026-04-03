"""
健康檢查端點
"""
import logging

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends

from app.init.container import AppContainer, get_container
from app.services.setup.device_service import DeviceService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """淺層健康檢查"""
    return {"status": "ok"}


@router.get("/health/deep")
async def deep_health_check():
    """
    深層健康檢查：驗證 DB 連線和 TaskManager 狀態。
    回傳各子系統狀態；任一 failed 則整體 status 為 degraded。
    """
    checks = {}

    # DB check
    try:
        from app.db.database import get_engine
        from sqlalchemy import text
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = {"status": "ok"}
    except Exception as e:
        logger.warning(f"Deep health: DB check failed: {e}")
        checks["db"] = {"status": "failed", "error": str(e)}

    # TaskManager check
    try:
        container = get_container()
        tm = container.task_manager()
        active = tm.get_active_tasks()
        checks["task_manager"] = {
            "status": "ok",
            "active_tasks": len(active),
        }
    except Exception as e:
        logger.warning(f"Deep health: TaskManager check failed: {e}")
        checks["task_manager"] = {"status": "failed", "error": str(e)}

    overall = "ok" if all(c["status"] == "ok" for c in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}


@router.get("/device")
@inject
async def device_info(
    service: DeviceService = Depends(Provide[AppContainer.device_service]),
):
    """取得裝置資訊（GPU/CPU）"""
    return service.get_device_info()


@router.post("/device/refresh")
@inject
async def refresh_device(
    service: DeviceService = Depends(Provide[AppContainer.device_service]),
):
    """清除裝置快取並重新偵測（CUDA DLL 安裝後呼叫）"""
    service.refresh_cache()
    return service.get_device_info()
