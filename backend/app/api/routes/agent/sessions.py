"""Agent session CRUD — persist/list/resume/delete agent conversations."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.agent.agent_session_service import AgentSessionService


router = APIRouter(prefix="/sessions")


class AppendMessageRequest(BaseModel):
    """One committed message appended to a session (lazily creates the session)."""
    role: str
    content: str = ""
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None


@router.get("")
@inject
async def list_sessions(
    svc: "AgentSessionService" = Depends(Provide[AppContainer.agent_session_service]),
):
    """List sessions for the master view, newest activity first."""
    return svc.list_sessions()


@router.get("/{session_id}/messages")
@inject
async def get_messages(
    session_id: str,
    svc: "AgentSessionService" = Depends(Provide[AppContainer.agent_session_service]),
):
    """Full ordered messages for resume. 404 if the session is unknown."""
    result = svc.get_messages(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="session not found")
    return result


@router.post("/{session_id}/messages")
@inject
async def append_message(
    session_id: str,
    request: AppendMessageRequest,
    svc: "AgentSessionService" = Depends(Provide[AppContainer.agent_session_service]),
):
    """Append one message; lazily creates the session on first append."""
    svc.append_message(
        session_id=session_id,
        role=request.role,
        content=request.content,
        tool_calls=request.tool_calls,
        tool_call_id=request.tool_call_id,
    )
    return {"ok": True}


@router.delete("/{session_id}")
@inject
async def delete_session(
    session_id: str,
    svc: "AgentSessionService" = Depends(Provide[AppContainer.agent_session_service]),
):
    """Delete a session + its messages. Idempotent."""
    svc.delete_session(session_id)
    return {"ok": True}
