from fastapi import APIRouter
from .status import router as status_router
from .models import router as models_router
from .config import router as config_router
from .remote import router as remote_router

router = APIRouter()
router.include_router(status_router)
router.include_router(models_router)
router.include_router(config_router)
router.include_router(remote_router)
