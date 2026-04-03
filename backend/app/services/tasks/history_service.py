"""
任務歷史紀錄服務
透過 TaskHistoryDAO 持久化已完成的任務，供跨 session 查詢
"""
import logging
from datetime import datetime
from typing import Optional

from app.db.dao.task_history_dao import TaskHistoryDAO

logger = logging.getLogger(__name__)


class TaskHistoryService:
    """任務歷史紀錄服務"""

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
        """儲存已完成的任務到歷史"""
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

    def query(
        self,
        page: int = 1,
        page_size: int = 30,
        status: Optional[str] = None,
    ) -> dict:
        """分頁查詢歷史紀錄"""
        return self._dao.query(page=page, page_size=page_size, status=status)

    def delete(self, task_id: str) -> bool:
        """刪除單筆歷史紀錄"""
        return self._dao.delete(task_id)

    def clear(self) -> int:
        """清空所有歷史紀錄"""
        return self._dao.clear()
