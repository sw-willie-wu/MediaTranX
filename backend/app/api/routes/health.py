"""
Health check endpoints.
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
    """Shallow health check."""
    return {"status": "ok"}


@router.get("/health/deep")
async def deep_health_check():
    """
    Deep health check: verify DB connection and TaskManager status.
    Returns per-subsystem status; overall status is degraded if any check fails.
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
    """Get device information (GPU/CPU)."""
    return service.get_device_info()


@router.post("/device/refresh")
@inject
async def refresh_device(
    service: DeviceService = Depends(Provide[AppContainer.device_service]),
):
    """Clear device cache and re-detect (called after CUDA DLL installation)."""
    service.refresh_cache()
    return service.get_device_info()
