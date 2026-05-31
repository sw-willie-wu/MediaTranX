"""
Agent session service.

Persists agent conversations via AgentSessionDAO and maps stored rows to the
frontend Message shape (role / content / toolCalls / toolCallId) for resume.
Owns timestamp generation (ISO-8601 UTC strings, per repo convention).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db.dao.agent_session_dao import AgentSessionDAO

logger = logging.getLogger(__name__)


class AgentSessionService:
    """Persistent agent-conversation service backed by AgentSessionDAO."""

    def __init__(self):
        self._dao = AgentSessionDAO()
        logger.info("AgentSessionService initialized")

    def list_sessions(self) -> list[dict]:
        """List rows for the master view (no message bodies), newest first."""
        return [
            {
                "id": s.id,
                "last_preview": s.last_preview,
                "updated_at": s.updated_at,
                "message_count": s.message_count,
            }
            for s in self._dao.list_sessions()
        ]

    def get_messages(self, session_id: str) -> Optional[dict]:
        """Full ordered messages in frontend Message shape, or None if unknown."""
        if self._dao.get_session(session_id) is None:
            return None
        msgs: list[dict] = []
        for r in self._dao.get_messages(session_id):
            if r.role == "assistant":
                m: dict = {"role": "assistant", "content": r.content}
                if r.tool_calls:
                    m["toolCalls"] = json.loads(r.tool_calls)
                msgs.append(m)
            elif r.role == "tool":
                msgs.append({"role": "tool", "content": r.content, "toolCallId": r.tool_call_id})
            else:
                msgs.append({"role": "user", "content": r.content})
        return {"id": session_id, "messages": msgs}

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        tool_calls: Optional[list] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Append one committed message; lazily creates the session row."""
        now_iso = datetime.now(timezone.utc).isoformat()
        self._dao.append_message(
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=json.dumps(tool_calls) if tool_calls else None,
            tool_call_id=tool_call_id,
            now_iso=now_iso,
        )

    def delete_session(self, session_id: str) -> None:
        """Delete a session + its messages. Idempotent (no error if missing)."""
        self._dao.delete_session(session_id)
