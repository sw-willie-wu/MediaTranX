"""
API-layer Pydantic model definitions.

TaskStatus and domain dataclasses are defined in app.models;
this module contains only Pydantic models for API serialization.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_serializer

from app.models.task import TaskData, TaskStatus  # noqa: F401 – re-export
from app.models.file import FileData


def _serialize_dt(v: datetime) -> str:
    return v.isoformat()


class TaskResponse(BaseModel):
    """Task API response model."""
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    _serialize_created_at = field_serializer("created_at")(_serialize_dt)
    _serialize_updated_at = field_serializer("updated_at")(_serialize_dt)

    @classmethod
    def from_task_data(cls, t: TaskData) -> TaskResponse:
        return cls(
            task_id=t.task_id,
            task_type=t.task_type,
            status=t.status,
            progress=t.progress,
            message=t.message,
            result=t.result,
            error=t.error,
            error_code=getattr(t, 'error_code', None),
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


class ProgressUpdate(BaseModel):
    """Progress update model (for SSE)."""
    task_id: str
    progress: float = Field(ge=0.0, le=1.0)
    stage: str = "processing"
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    _serialize_timestamp = field_serializer("timestamp")(_serialize_dt)


class FileInfo(BaseModel):
    """File API response model."""
    file_id: str
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    source_dir: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None

    _serialize_created_at = field_serializer("created_at")(_serialize_dt)

    @classmethod
    def from_file_data(cls, f: FileData) -> FileInfo:
        return cls(
            file_id=f.file_id,
            filename=f.filename,
            original_filename=f.original_filename,
            file_path=f.file_path,
            file_size=f.file_size,
            mime_type=f.mime_type,
            source_dir=f.source_dir,
            created_at=f.created_at,
            metadata=f.metadata,
        )


class FileUploadResponse(BaseModel):
    """File upload response."""
    file_id: str
    filename: str
    file_size: int
    mime_type: str


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
