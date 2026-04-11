"""PDF / document conversion API routes."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.document.pdf_convert_service import DocumentPdfConvertService

router = APIRouter()


class PdfConvertRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    output_format: str = Field(default="txt", description="Output format: txt / md / images")
    output_dir: Optional[str] = Field(default=None)
    output_filename: Optional[str] = Field(default=None)


@router.post("/pdf-convert")
@inject
async def convert_document(
    request: PdfConvertRequest,
    service: DocumentPdfConvertService = Depends(Provide[AppContainer.doc_pdf_convert]),
):
    """Submit document conversion task."""
    try:
        task_id = await service.submit(
            file_id=request.file_id,
            output_format=request.output_format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return {"task_id": task_id, "message": "Conversion task submitted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
