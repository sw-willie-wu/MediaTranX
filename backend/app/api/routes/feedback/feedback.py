"""問題回報 API。endpoint 用 sync def（FastAPI 丟 threadpool），
transport 的 blocking urlopen 不會卡 event loop。"""
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.feedback.diagnostics import DiagnosticsSections
from app.services.feedback.service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackBody(BaseModel):
    type: str = Field(..., description="bug | feature | other")
    description: str
    email: str | None = None
    include_diagnostics: bool = False
    diagnostics: DiagnosticsSections | None = None


class ExportResponse(BaseModel):
    zip_path: str


@router.post("", status_code=204)
@inject
def submit_feedback(
    body: FeedbackBody,
    service: FeedbackService = Depends(Provide[AppContainer.feedback]),
):
    service.submit(
        type=body.type,
        description=body.description,
        email=body.email,
        include_diagnostics=body.include_diagnostics,
        diagnostics=body.diagnostics,
    )


@router.get("/diagnostics", response_model=DiagnosticsSections)
@inject
def get_diagnostics(
    task_id: str | None = None,
    service: FeedbackService = Depends(Provide[AppContainer.feedback]),
):
    return service.get_diagnostics(task_id)


@router.post("/diagnostics/export", response_model=ExportResponse)
@inject
def export_diagnostics(
    service: FeedbackService = Depends(Provide[AppContainer.feedback]),
):
    return ExportResponse(zip_path=service.export_diagnostics())
