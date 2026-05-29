"""
Agent session DAO.

Append-only persistence for agent conversations. append_message lazily creates
the session row on first append and maintains seq/message_count/preview/updated_at.
"""
import logging

from sqlmodel import Session, select

from app.db.database import get_engine
from app.db.models.agent_session import AgentSession
from app.db.models.agent_message import AgentMessage

logger = logging.getLogger(__name__)

_PREVIEW_MAX = 200


class AgentSessionDAO:
    """Agent conversation data access."""

    def list_sessions(self) -> list[AgentSession]:
        """All sessions, newest activity first."""
        with Session(get_engine()) as session:
            stmt = select(AgentSession).order_by(AgentSession.updated_at.desc())
            return list(session.exec(stmt).all())

    def get_session(self, session_id: str) -> AgentSession | None:
        with Session(get_engine()) as session:
            return session.get(AgentSession, session_id)

    def get_messages(self, session_id: str) -> list[AgentMessage]:
        """Ordered messages for a session (empty list if none)."""
        with Session(get_engine()) as session:
            stmt = (
                select(AgentMessage)
                .where(AgentMessage.session_id == session_id)
                .order_by(AgentMessage.seq)
            )
            return list(session.exec(stmt).all())

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: str | None,
        tool_call_id: str | None,
        now_iso: str,
    ) -> AgentMessage:
        """Append one message; lazily create the session on first append.

        seq is assigned = current message_count (monotonic, no gaps under the
        single-writer rule). Bumps message_count/updated_at; updates last_preview.
        """
        with Session(get_engine()) as session:
            sess = session.get(AgentSession, session_id)
            if sess is None:
                sess = AgentSession(
                    id=session_id,
                    created_at=now_iso,
                    updated_at=now_iso,
                    message_count=0,
                    last_preview="",
                )
                session.add(sess)
                session.flush()  # ensure the row exists before we read its count

            seq = sess.message_count
            msg = AgentMessage(
                session_id=session_id,
                seq=seq,
                role=role,
                content=content,
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
                created_at=now_iso,
            )
            session.add(msg)

            sess.message_count = seq + 1
            sess.updated_at = now_iso
            sess.last_preview = (content or "")[:_PREVIEW_MAX]
            session.add(sess)

            session.commit()
            session.refresh(msg)
            return msg

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages (manual cascade). Idempotent."""
        with Session(get_engine()) as session:
            sess = session.get(AgentSession, session_id)
            if sess is None:
                return False
            rows = session.exec(
                select(AgentMessage).where(AgentMessage.session_id == session_id)
            ).all()
            for row in rows:
                session.delete(row)
            session.delete(sess)
            session.commit()
            return True
