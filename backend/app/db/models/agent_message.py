"""
Agent chat message model.

Append-only, one row per committed user/assistant/tool message. tool_calls is a
JSON-encoded array for assistant rows that carry tool calls; tool_call_id is set
for tool rows.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentMessage(SQLModel, table=True):
    """A single committed message in an agent conversation."""
    __tablename__ = "agent_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, foreign_key="agent_sessions.id")
    seq: int  # monotonic per session; backend-assigned = count at append
    role: str  # 'user' | 'assistant' | 'tool'
    content: str = ""
    tool_calls: Optional[str] = None  # JSON-encoded array (assistant rows)
    tool_call_id: Optional[str] = None  # for role='tool' rows
    created_at: str = Field(default_factory=_now_iso)  # ISO 8601
