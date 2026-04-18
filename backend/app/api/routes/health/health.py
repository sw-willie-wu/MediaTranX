"""Shallow + deep health check endpoints."""
from __future__ import annotations
import logging

from fastapi import APIRouter

from app.init.container import get_container

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """Shallow health check."""
    return {"status": "ok"}


@router.get("/health/deep")
async def deep_health_check():
    """Deep health check.

    Returns per-subsystem status; overall status is 'degraded' if any check fails.
    This endpoint intentionally captures probe exceptions as JSON (unhealthy state)
    rather than raising — the try/except are part of the probe contract, not
    error-to-HTTP mapping that spec §5.2 forbids.
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
