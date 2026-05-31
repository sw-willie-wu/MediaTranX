"""Agent run endpoint — streams AG-UI SSE events for one LLM round."""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

# RunAgentInput must be imported at module level (not under TYPE_CHECKING)
# because FastAPI's Pydantic body validation resolves the type at request time.
# AgentService can stay under TYPE_CHECKING since dependency_injector resolves
# the actual class lazily.
from ag_ui.core import RunAgentInput

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.agent.agent_service import AgentService


router = APIRouter()


@router.post("/run")
@inject
async def run_agent(
    request: Request,
    input: RunAgentInput,
    svc: "AgentService" = Depends(Provide[AppContainer.agent_service]),
):
    """Stream AG-UI SSE events for one LLM round.

    Request body: RunAgentInput (Pydantic model from ag_ui.core).
    Response: text/event-stream of camelCase JSON events
              (RUN_STARTED, TEXT_MESSAGE_CHUNK, TOOL_CALL_CHUNK,
               RUN_FINISHED, RUN_ERROR).
    Client disconnect mid-stream → AgentService.run() finally hook
    calls session.kill_process() (no extra handling needed in route).
    """
    accept = request.headers.get("accept")
    return StreamingResponse(
        svc.run(input, accept=accept),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx-style buffering
        },
    )
