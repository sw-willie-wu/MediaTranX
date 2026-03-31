"""
任務歷史紀錄 Model
"""
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class TaskHistory(SQLModel, table=True):
    """任務歷史紀錄"""
    __tablename__ = "task_history"

    task_id: str = Field(primary_key=True)
    task_type: str
    label: Optional[str] = None
    file_name: Optional[str] = None
    status: str
    error: Optional[str] = None
    error_code: Optional[str] = None  # RemoteApiError code for i18n
    result: Optional[str] = None  # JSON string
    created_at: str  # ISO 8601
    completed_at: str  # ISO 8601
