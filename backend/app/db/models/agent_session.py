"""
Agent chat session model.

One row per persisted agent conversation. `id` doubles as the AG-UI thread_id.
RAG-ready: stable normalized rows; future embeddings attach via a separate table.
"""
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentSession(SQLModel, table=True):
    """A persisted agent conversation (= one AG-UI thread)."""
    __tablename__ = "agent_sessions"

    id: str = Field(primary_key=True)  # uuid; also the AG-UI thread_id
    created_at: str = Field(default_factory=_now_iso)  # ISO 8601
    updated_at: str = Field(default_factory=_now_iso)  # ISO 8601
    message_count: int = Field(default=0)
    last_preview: str = Field(default="")  # truncated last-message text for the list row
