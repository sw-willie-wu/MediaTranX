"""
Task history service.
Persists completed tasks via TaskHistoryDAO for cross-session queries.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db.dao.task_history_dao import TaskHistoryDAO

logger = logging.getLogger(__name__)


class TaskHistoryService:
    """Persistent task history service backed by TaskHistoryDAO."""

    def __init__(self):
        self._dao = TaskHistoryDAO()
        logger.info("TaskHistoryService initialized")

    def save(
        self,
        task_id: str,
        task_type: str,
        status: str,
        created_at: datetime,
        completed_at: datetime,
        label: Optional[str] = None,
        file_name: Optional[str] = None,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> None:
        """Save a completed task to history."""
        self._dao.save(
            task_id=task_id,
            task_type=task_type,
            status=status,
            created_at=created_at,
            completed_at=completed_at,
            label=label,
            file_name=file_name,
            error=error,
            error_code=error_code,
            result=result,
        )

    def save_frontend_task(
        self,
        task_id: str,
        task_type: str,
        status: str,
        label: Optional[str] = None,
        file_name: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> None:
        """Save a frontend-only task (e.g. MIDI export) to history."""
        now = datetime.now(timezone.utc)
        self.save(
            task_id=task_id,
            task_type=task_type,
            status=status,
            created_at=now,
            completed_at=now,
            label=label,
            file_name=file_name,
            error=error,
            result=result,
        )

    def query(
        self,
        page: int = 1,
        page_size: int = 30,
        status: Optional[str] = None,
    ) -> dict:
        """Query history records with pagination."""
        return self._dao.query(page=page, page_size=page_size, status=status)

    def delete(self, task_id: str) -> None:
        """Delete a single history record. Raises NotFoundError if missing."""
        from app.handler.exceptions import NotFoundError

        if not self._dao.delete(task_id):
            raise NotFoundError(f"History item not found: {task_id}")

    def clear(self) -> int:
        """Clear all history records."""
        return self._dao.clear()
