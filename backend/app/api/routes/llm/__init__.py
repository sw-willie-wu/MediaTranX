"""LLM routes aggregator."""
from fastapi import APIRouter

from .chat import router as chat_router
from .translate import router as translate_router

router = APIRouter()
router.include_router(translate_router)
router.include_router(chat_router)
