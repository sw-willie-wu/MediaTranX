"""
API 層 Pydantic 模型定義

TaskStatus 和 domain dataclasses 定義於 app.models，
此處僅放 API 序列化用的 Pydantic models。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.task import TaskData, TaskStatus  # noqa: F401 – re-export
from app.models.file import FileData


class TaskResponse(BaseModel):
    """任務 API 回應模型"""
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

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
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


class ProgressUpdate(BaseModel):
    """進度更新模型（用於 SSE）"""
    task_id: str
    progress: float = Field(ge=0.0, le=1.0)
    stage: str = "processing"
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class FileInfo(BaseModel):
    """檔案 API 回應模型"""
    file_id: str
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    source_dir: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None

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
    """檔案上傳回應"""
    file_id: str
    filename: str
    file_size: int
    mime_type: str


class ErrorResponse(BaseModel):
    """錯誤回應模型"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
