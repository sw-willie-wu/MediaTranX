"""Files routes aggregator.

`list_files` (GET "") is registered directly on this aggregator router because
FastAPI rejects an empty prefix + empty path combination when including a
sub-router. All other file endpoints live in their own feature modules.
"""
from fastapi import APIRouter

from .browse import FileInfo, list_files, router as browse_router
from .cleanup import router as cleanup_router
from .download import router as download_router
from .register import router as register_router
from .upload import router as upload_router

router = APIRouter()
router.include_router(upload_router)
router.include_router(register_router)
router.include_router(browse_router)
router.include_router(download_router)
router.include_router(cleanup_router)

# Register list_files directly (see module docstring for rationale).
router.get("", response_model=list[FileInfo])(list_files)
