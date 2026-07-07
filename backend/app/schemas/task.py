"""
Cross-layer shared task domain models.

TaskStatus and TaskData are shared by workers, services, and api layers
to avoid workers depending on the API layer.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from app.handler.exceptions import TaskCancelledError  # noqa: F401 — re-export for back-compat


class TaskStatus(str, Enum):
    """Task status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskData:
    """Task internal state (mutable dataclass, used by TaskManager)."""
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    message: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    notices: list = field(default_factory=list)  # [{"code": str, "params": dict}]
    file_id: Optional[str] = None  # input file the task processes (for response-time name resolution)
    suppress_results: bool = False  # pipeline intermediate: force outputs out of the Results drawer
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
