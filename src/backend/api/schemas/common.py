"""
通用 Pydantic 模型定義
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任務狀態"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskResponse(BaseModel):
    """任務回應模型"""
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
    """檔案資訊模型"""
    file_id: str
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None


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
