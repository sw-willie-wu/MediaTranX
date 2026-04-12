"""
LLM shared API routes.
Translate languages, styles, model status — shared across all domain workflows.
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.setup.language_service import LanguageService

router = APIRouter()


# ── Translate languages & styles ──

@router.get("/translate/languages")
@inject
async def get_translate_languages(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Get the list of languages supported by translation models."""
    return language_service.get_supported_languages()


@router.get("/translate/styles")
@inject
async def get_translate_styles(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Get list of translation style options."""
    return language_service.get_translate_styles()


# ── Model status ──

@router.get("/translate/status")
@inject
async def get_translate_model_status(
    model_family: str = "gemma4",
    model_size: str = "4b",
    quantization: str | None = None,
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Query translation model download/availability status."""
    try:
        status = language_service.get_model_status(model_family, model_size, quantization)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Dev test ──

# ── Chat (dev test) ──

class ChatRequest(BaseModel):
    """LLM chat request. Sends prompt directly to model for testing."""
    prompt: str = Field(..., description="Full prompt text (sent as-is to model)")
    model_family: str = Field(default="gemma4", description="Model family")
    model_size: str = Field(default="8b", description="Model size")
    thinking: bool = Field(default=False, description="Enable thinking mode (Qwen3)")
    max_tokens: int = Field(default=4096, description="Max output tokens")
    temperature: float = Field(default=0.1, description="Sampling temperature")


class ChatResponse(BaseModel):
    """LLM chat response."""
    result: str


@router.post("/chat", response_model=ChatResponse)
@inject
async def llm_chat(request: ChatRequest):
    """
    Dev test endpoint — sends prompt directly to local LLM.
    Uses per-model inference config for top_k/top_p but prompt is sent as-is.
    """
    try:
        from app.engine.ai.runtime.llama_server import LlamaServerRuntime
        from app.engine.ai.registry import SLOT_LLM

        runtime = LlamaServerRuntime(SLOT_LLM)
        with runtime.acquire(request.model_family, request.model_size):
            output = runtime.chat(
                messages=[{"role": "user", "content": request.prompt}],
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        return ChatResponse(result=output)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
