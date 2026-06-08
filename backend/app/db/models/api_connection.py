"""
Remote API connection settings model.
"""
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class ApiConnection(SQLModel, table=True):
    """Remote API connection settings."""
    __tablename__ = "api_connections"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)  # ollama, openai, gemini
    name: str  # Display name (e.g. "Local Ollama", "My GPT Key")
    endpoint: str  # API endpoint URL
    api_key: Optional[str] = None  # API key / token (not required for ollama)
    enabled: bool = Field(default=True)
    chunk_ctx_budget: Optional[int] = None  # null = auto（依模型偵測 max 切 chunk）
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
