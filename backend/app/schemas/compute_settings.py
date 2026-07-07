"""Compute-policy settings (GPU→CPU fallback toggle), persisted in app_settings."""
from typing import Optional

from pydantic import BaseModel, Field


class ComputeSettings(BaseModel):
    """User compute policy. Default ON preserves the legacy silent-downgrade UX."""
    allow_cpu_fallback: bool = True
    max_concurrent_tasks: int = Field(default=4, ge=1, le=8)


class ComputeSettingsUpdate(BaseModel):
    """Patch model — None means 'leave unchanged'."""
    allow_cpu_fallback: Optional[bool] = None
    max_concurrent_tasks: Optional[int] = Field(default=None, ge=1, le=8)
