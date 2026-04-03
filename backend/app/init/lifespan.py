"""
Application lifespan — startup and shutdown hooks.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.init.container import get_container

LOGGER = logging.getLogger(__name__)


def _warmup_services(container) -> None:
    """Pre-initialize setup-critical services so settings page loads instantly."""
    container.config_service()
    container.language_service()
    container.remote_service()
    container.model_manager()
    container.model_metadata()
    container.device_service()
    LOGGER.info("Setup services pre-warmed")


def build_lifespan():
    """Build a lifespan context manager for the FastAPI app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ── Startup ──
        init_db()
        LOGGER.info("Database initialized")

        container = get_container()
        history = container.task_history()
        tm = container.task_manager()

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

        _warmup_services(container)

        yield

        # ── Shutdown ──
        LOGGER.info("Shutting down...")
        tm.shutdown()

        fs = container.file_service()
        fs.cleanup_all()
        LOGGER.info("Shutdown complete")

    return lifespan
