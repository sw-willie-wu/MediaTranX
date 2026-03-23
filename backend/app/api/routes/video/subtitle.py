"""
字幕提取 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.video.subtitle_service import get_subtitle_service
from app.services.setup.language_service import get_language_service

router = APIRouter()


class SubtitleGenerateRequest(BaseModel):
    """字幕生成請求"""
    file_id: str = Field(..., description="輸入影片檔案 ID")
    language: Optional[str] = Field(
        default=None,
        description="語言代碼 (None=自動偵測, zh=中文, en=英文, ja=日文...)"
    )
    model_size: str = Field(
        default="medium",
        description="模型大小 (tiny, base, small, medium, large-v3)"
    )
    output_format: str = Field(
        default="srt",
        description="輸出格式 (srt, vtt)"
    )
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")
    target_language: Optional[str] = Field(
        default=None,
        description="翻譯目標語言 (None=不翻譯, zh-TW=繁體中文, en=英文...)"
    )
    translate_model_size: str = Field(
        default="4b",
        description="翻譯模型大小 (4b, 12b, 27b)"
    )
    translate_model_type: str = Field(
        default="translategemma",
        description="翻譯模型類型 (translategemma, qwen3)"
    )
    translate_quantization: Optional[str] = Field(
        default=None,
        description="翻譯模型量化精度 (Q4_K_M, Q4_K_S, Q3_K_L, Q3_K_M, Q3_K_S, Q8_0 等)"
    )
    # 進階分句參數
    word_timestamps: bool = Field(
        default=False,
        description="啟用詞級時間戳（有助於更精確分句）"
    )
    condition_on_previous_text: bool = Field(
        default=True,
        description="根據前文調整辨識（關閉可避免句子合併，適合多人對話）"
    )
    min_silence_duration_ms: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="最小靜音時長（毫秒），低於此值的停頓不會分句"
    )
    vad_threshold: float = Field(
        default=0.5,
        ge=0.1,
        le=0.9,
        description="VAD 門檻值，越低越敏感（更容易分句）"
    )
    # 翻譯選項
    keep_names: bool = Field(
        default=True,
        description="保留人名和專有名詞原文"
    )
    translate_style: str = Field(
        default="colloquial",
        description="翻譯風格：colloquial（口語化）、formal（正式）、literal（直譯）"
    )
    glossary: Optional[dict[str, str]] = Field(
        default=None,
        description="專有名詞對照表 {原文: 譯文}"
    )


class SubtitleGenerateResponse(BaseModel):
    """字幕生成回應"""
    task_id: str
    message: str = "字幕生成任務已提交"


class ModelStatusResponse(BaseModel):
    """模型狀態回應（僅套件可用性 + 模型是否已下載）"""
    available: bool
    model_size: str
    model_downloaded: bool


@router.get("/whisper/status", response_model=ModelStatusResponse)
async def get_whisper_status(model_size: str = "medium"):
    """查詢 Whisper 模型狀態"""
    try:
        service = get_subtitle_service()
        status = service.get_model_status(model_size)
        return ModelStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translategemma/status", response_model=ModelStatusResponse)
async def get_translategemma_status(model_size: str = "4b"):
    """查詢 TranslateGemma 模型狀態"""
    try:
        status = get_language_service().get_model_status("translategemma", model_size)
        return ModelStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translate/status")
async def get_translate_model_status(model_type: str = "translategemma", model_size: str = "4b", quantization: str | None = None):
    """查詢翻譯模型狀態（通用，支援 translategemma 和 qwen3）"""
    try:
        status = get_language_service().get_model_status(model_type, model_size, quantization)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translategemma/languages")
async def get_translategemma_languages():
    """取得翻譯模型支援的翻譯語言列表"""
    return get_language_service().get_supported_languages()


class TranslateTestResponse(BaseModel):
    """翻譯測試回應"""
    result: str
    prompt: str


class TranslateTestRequest(BaseModel):
    """翻譯測試請求"""
    text: str = Field(..., description="要翻譯的文字（可以是 SRT 格式）")
    target_language: str = Field(default="zh-TW", description="目標語言")
    source_language: str = Field(default="ja", description="來源語言")
    model_size: str = Field(default="4b", description="模型大小: 4b, 12b")


@router.post("/translategemma/test", response_model=TranslateTestResponse)
async def test_translate(request: TranslateTestRequest):
    """
    測試翻譯（開發用）— 使用 llama-server messages API
    """
    try:
        from app.utils.prompts import LANG_NAMES_EN
        from app.engine.ai.runtime.llama_server import LlamaServerRuntime
        from app.engine.ai.registry import SLOT_LLM

        source_name = LANG_NAMES_EN.get(request.source_language, request.source_language)
        target_name = LANG_NAMES_EN.get(request.target_language, request.target_language)
        variant = request.model_size

        user_msg = (
            f"Translate the following {source_name} subtitles to {target_name}. "
            f"Keep SRT format and timestamps unchanged. Output only the translation.\n\n"
            f"{request.text}"
        )
        messages = [{"role": "user", "content": user_msg}]

        runtime = LlamaServerRuntime(SLOT_LLM)
        with runtime.acquire("translategemma", variant):
            result = runtime.chat(
                messages=messages,
                max_tokens=len(request.text) * 3,
                temperature=0.1,
            )

        return TranslateTestResponse(result=result, prompt=user_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subtitle/generate", response_model=SubtitleGenerateResponse)
async def generate_subtitle(request: SubtitleGenerateRequest):
    """
    提交字幕生成任務

    使用 faster-whisper 從影片中提取語音並生成字幕檔。
    首次使用時會自動下載指定大小的模型。
    可選擇翻譯字幕到指定語言。

    支援的選項：
    - **language**: None (自動偵測), zh, en, ja, ko, fr, de, es...
    - **model_size**: tiny, base, small, medium (推薦), large-v3
    - **output_format**: srt (預設), vtt
    - **target_language**: None (不翻譯), zh-TW, en, ja...
    - **translate_model_size**: 4b (推薦), 12b, 27b

    進階分句選項（適合多人對話場景）：
    - **word_timestamps**: 啟用詞級時間戳
    - **condition_on_previous_text**: 關閉可避免句子合併
    - **min_silence_duration_ms**: 最小靜音時長 (100-2000ms)
    - **vad_threshold**: VAD 門檻值 (0.1-0.9)
    """
    try:
        service = get_subtitle_service()
        task_id = await service.submit_subtitle_generate(
            file_id=request.file_id,
            language=request.language,
            model_size=request.model_size,
            output_format=request.output_format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
            target_language=request.target_language,
            translate_model_size=request.translate_model_size,
            translate_model_type=request.translate_model_type,
            translate_quantization=request.translate_quantization,
            word_timestamps=request.word_timestamps,
            condition_on_previous_text=request.condition_on_previous_text,
            min_silence_duration_ms=request.min_silence_duration_ms,
            vad_threshold=request.vad_threshold,
            keep_names=request.keep_names,
            translate_style=request.translate_style,
            glossary=request.glossary,
        )
        return SubtitleGenerateResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
