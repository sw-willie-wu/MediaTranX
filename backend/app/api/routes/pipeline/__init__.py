from fastapi import APIRouter

from .recipes import router as recipes_router

router = APIRouter()
router.include_router(recipes_router)
