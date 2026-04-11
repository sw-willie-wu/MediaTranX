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
    label: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
