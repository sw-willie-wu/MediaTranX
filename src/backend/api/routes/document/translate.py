"""
文件翻譯 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.document.translate_service import get_translate_service
from backend.core.ai.base_translator import SUPPORTED_LANGUAGES
from backend.core.ai.translation import get_translator

router = APIRouter()


class DocumentTranslateRequest(BaseModel):
    """文件翻譯請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    source_language: str = Field(..., description="來源語言 (BCP 47)")
    target_language: str = Field(..., description="目標語言 (BCP 47)")
    model_size: str = Field(default="4b", description="模型大小 (4b, 12b, 27b)")
    model_type: str = Field(default="translategemma", description="翻譯模型類型 (translategemma, qwen3)")
    quantization: Optional[str] = Field(default=None, description="模型量化精度 (Q4_K_M, Q3_K_M 等)")
    glossary: Optional[dict[str, str]] = Field(default=None, description="專有名詞對照表 {原文: 譯文}")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class DocumentTranslateResponse(BaseModel):
    """文件翻譯回應"""
    task_id: str
    message: str = "文件翻譯任務已提交"


class TranslateGemmaStatusResponse(BaseModel):
    """TranslateGemma 模型狀態回應"""
    available: bool
    model_size: str
    model_downloaded: bool
    device: str
    compute_type: str
    device_name: str


@router.get("/translategemma/status", response_model=TranslateGemmaStatusResponse)
async def get_translategemma_status(model_type: str = "translategemma", model_size: str = "4b"):
    """查詢翻譯模型狀態"""
    try:
        translator = get_translator(model_type)
        status = translator.get_model_status(model_size)
        return TranslateGemmaStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translategemma/languages")
async def get_translategemma_languages():
    """取得 TranslateGemma 支援的翻譯語言列表"""
    return SUPPORTED_LANGUAGES


@router.post("/translate", response_model=DocumentTranslateResponse)
async def translate_document(request: DocumentTranslateRequest):
    """
    提交文件翻譯任務

    使用 TranslateGemma 翻譯上傳的文字檔。
    首次使用時會自動下載指定大小的模型。
    """
    try:
        service = get_translate_service()
        task_id = await service.submit_translate(
            file_id=request.file_id,
            source_language=request.source_language,
            target_language=request.target_language,
            model_size=request.model_size,
            model_type=request.model_type,
            quantization=request.quantization,
            glossary=request.glossary,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return DocumentTranslateResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
