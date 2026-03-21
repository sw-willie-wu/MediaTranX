"""
任務歷史紀錄服務
透過共用 Database 模組持久化已完成的任務，供跨 session 查詢
"""
import json
import logging
from datetime import datetime
from typing import Optional

from app.engine.database import get_database

logger = logging.getLogger(__name__)


class TaskHistoryService:
    """任務歷史紀錄服務（單例）"""

    _instance: Optional["TaskHistoryService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._db = get_database()
        self._init_schema()
        self._initialized = True
        logger.info("TaskHistoryService initialized")

    def _init_schema(self) -> None:
        self._db.init_table("""
            CREATE TABLE IF NOT EXISTS task_history (
                task_id      TEXT PRIMARY KEY,
                task_type    TEXT NOT NULL,
                label        TEXT,
                file_name    TEXT,
                status       TEXT NOT NULL,
                error        TEXT,
                result       TEXT,
                created_at   TEXT NOT NULL,
                completed_at TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_history_created
            ON task_history (created_at DESC)
        """)
        self._db.commit()

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
        result: Optional[dict] = None,
    ) -> None:
        """儲存已完成的任務到歷史"""
        self._db.execute(
            """
            INSERT OR REPLACE INTO task_history
                (task_id, task_type, label, file_name, status, error, result, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                label,
                file_name,
                status,
                error,
                json.dumps(result) if result else None,
                created_at.isoformat(),
                completed_at.isoformat(),
            ),
        )
        self._db.commit()

    def query(
        self,
        page: int = 1,
        page_size: int = 30,
        status: Optional[str] = None,
    ) -> dict:
        """
        分頁查詢歷史紀錄

        Returns:
            {"items": [...], "total": int, "page": int, "page_size": int}
        """
        where = ""
        params: list = []
        if status:
            where = "WHERE status = ?"
            params.append(status)

        total = self._db.fetchone(
            f"SELECT COUNT(*) FROM task_history {where}", params
        )[0]

        offset = (page - 1) * page_size
        rows = self._db.fetchall(
            f"""
            SELECT * FROM task_history {where}
            ORDER BY completed_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )

        items = []
        for row in rows:
            item = dict(row)
            if item.get("result"):
                try:
                    item["result"] = json.loads(item["result"])
                except (json.JSONDecodeError, TypeError):
                    pass
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def delete(self, task_id: str) -> bool:
        """刪除單筆歷史紀錄"""
        cursor = self._db.execute(
            "DELETE FROM task_history WHERE task_id = ?", (task_id,)
        )
        self._db.commit()
        return cursor.rowcount > 0

    def clear(self) -> int:
        """清空所有歷史紀錄"""
        cursor = self._db.execute("DELETE FROM task_history")
        self._db.commit()
        return cursor.rowcount


_task_history_service: Optional[TaskHistoryService] = None


def get_task_history_service() -> TaskHistoryService:
    global _task_history_service
    if _task_history_service is None:
        _task_history_service = TaskHistoryService()
    return _task_history_service
