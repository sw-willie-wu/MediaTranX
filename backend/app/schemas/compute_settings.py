"""Compute-policy settings (GPU→CPU fallback toggle), persisted in app_settings."""
from typing import Optional

from pydantic import BaseModel


class ComputeSettings(BaseModel):
    """User compute policy. Default ON preserves the legacy silent-downgrade UX."""
    allow_cpu_fallback: bool = True


class ComputeSettingsUpdate(BaseModel):
    """Patch model — None means 'leave unchanged'."""
    allow_cpu_fallback: Optional[bool] = None
