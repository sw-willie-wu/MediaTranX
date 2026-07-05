"""
Task history DAO.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select, func

from app.db.database import get_engine
from app.db.models.task_history import TaskHistory

logger = logging.getLogger(__name__)


class TaskHistoryDAO:
    """Task history data access."""

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
        with Session(get_engine()) as session:
            existing = session.get(TaskHistory, task_id)
            if existing:
                existing.task_type = task_type
                existing.label = label
                existing.file_name = file_name
                existing.status = status
                existing.error = error
                existing.error_code = error_code
                existing.result = json.dumps(result) if result else None
                existing.created_at = created_at.isoformat()
                existing.completed_at = completed_at.isoformat()
            else:
                record = TaskHistory(
                    task_id=task_id,
                    task_type=task_type,
                    label=label,
                    file_name=file_name,
                    status=status,
                    error=error,
                    error_code=error_code,
                    result=json.dumps(result) if result else None,
                    created_at=created_at.isoformat(),
                    completed_at=completed_at.isoformat(),
                )
                session.add(record)
            session.commit()

    def query(
        self,
        page: int = 1,
        page_size: int = 30,
        status: Optional[str] = None,
    ) -> dict:
        """Query history records with pagination."""
        with Session(get_engine()) as session:
            # Count
            count_stmt = select(func.count()).select_from(TaskHistory)
            if status:
                count_stmt = count_stmt.where(TaskHistory.status == status)
            total = session.exec(count_stmt).one()

            # Query
            stmt = select(TaskHistory).order_by(TaskHistory.completed_at.desc())
            if status:
                stmt = stmt.where(TaskHistory.status == status)
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
            rows = session.exec(stmt).all()

            items = []
            for row in rows:
                item = row.model_dump()
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

    def get(self, task_id: str) -> TaskHistory | None:
        """依 task_id 取單筆歷史（找不到回 None）。"""
        with Session(get_engine()) as session:
            return session.get(TaskHistory, task_id)

    def delete(self, task_id: str) -> bool:
        """Delete a single history record."""
        with Session(get_engine()) as session:
            record = session.get(TaskHistory, task_id)
            if record:
                session.delete(record)
                session.commit()
                return True
            return False

    def clear(self) -> int:
        """Clear all history records."""
        with Session(get_engine()) as session:
            stmt = select(TaskHistory)
            rows = session.exec(stmt).all()
            count = len(rows)
            for row in rows:
                session.delete(row)
            session.commit()
            return count
