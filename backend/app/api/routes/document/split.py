"""PDF split API routes."""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.document.split_service import DocumentSplitService

router = APIRouter()


class DocumentSplitRequest(BaseModel):
    file_id: str = Field(..., description="Input PDF file ID")
    pages: str = Field(default="", description="Page range, e.g. '1-3,5,7-9'; empty means all pages")
    suppress_results: bool = False


@router.post("/split")
@inject
async def split_document(
    request: DocumentSplitRequest,
    service: DocumentSplitService = Depends(Provide[AppContainer.doc_split]),
):
    """Submit PDF split task."""
    task_id = await service.submit(
        file_id=request.file_id,
        pages=request.pages,
        suppress_results=request.suppress_results,
    )
    return {"task_id": task_id, "message": "PDF split task submitted"}
