"""LLM chat endpoint."""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.llm.chat_service import ChatService


class ChatRequest(BaseModel):
    """LLM chat request."""
    prompt: str = Field(..., description="Full prompt text (sent as-is to model)")
    model_family: str = Field(default="gemma4", description="Model family")
    model_size: str = Field(default="8b", description="Model size")
    max_tokens: int = Field(default=4096, description="Max output tokens")
    temperature: float = Field(default=0.1, description="Sampling temperature")


class ChatResponse(BaseModel):
    """LLM chat response."""
    result: str


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@inject
async def llm_chat(
    request: ChatRequest,
    service: ChatService = Depends(Provide[AppContainer.chat_service]),
):
    """Send a prompt directly to a local LLM."""
    output = service.chat(
        prompt=request.prompt,
        model_family=request.model_family,
        model_size=request.model_size,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
    )
    return ChatResponse(result=output)
