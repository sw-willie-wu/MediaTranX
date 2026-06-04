"""User-adjustable Ollama inference settings, persisted in app_settings.

The num_ctx cap is the second, user-controllable ceiling on the
`options.num_ctx` we send to Ollama (issue #4's model-real-ctx clamp is the
first). num_ctx = min(needed, CAP, model_ctx).
"""
from typing import Optional

from pydantic import BaseModel, Field

_NUM_CTX_MIN = 4096    # a CAP below _NUM_CTX_FLOOR (4096) would be overridden by FLOOR anyway
_NUM_CTX_MAX = 131072


class OllamaSettings(BaseModel):
    """User-adjustable Ollama inference settings."""
    ollama_num_ctx_cap: int = Field(8192, ge=_NUM_CTX_MIN, le=_NUM_CTX_MAX)


class OllamaSettingsUpdate(BaseModel):
    """Patch model — None means 'leave unchanged'."""
    ollama_num_ctx_cap: Optional[int] = Field(None, ge=_NUM_CTX_MIN, le=_NUM_CTX_MAX)
