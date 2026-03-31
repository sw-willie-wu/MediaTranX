"""
Remote API 連線設定 Model
"""
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class ApiConnection(SQLModel, table=True):
    """Remote API 連線設定"""
    __tablename__ = "api_connections"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)  # ollama, openai, gemini
    name: str  # 顯示名稱（例如 "Local Ollama", "My GPT Key"）
    endpoint: str  # API endpoint URL
    api_key: Optional[str] = None  # API key / token（ollama 不需要）
    enabled: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
