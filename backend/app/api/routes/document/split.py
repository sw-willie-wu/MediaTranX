"""PDF split API routes."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.document.split_service import DocumentSplitService

router = APIRouter()


class DocumentSplitRequest(BaseModel):
    file_id: str = Field(..., description="Input PDF file ID")
    pages: str = Field(default="", description="Page range, e.g. '1-3,5,7-9'; empty means all pages")
    output_dir: Optional[str] = Field(default=None)
    output_filename: Optional[str] = Field(default=None)


@router.post("/split")
@inject
async def split_document(
    request: DocumentSplitRequest,
    service: DocumentSplitService = Depends(Provide[AppContainer.doc_split]),
):
    """Submit PDF split task."""
    try:
        task_id = await service.submit(
            file_id=request.file_id,
            pages=request.pages,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return {"task_id": task_id, "message": "PDF split task submitted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
