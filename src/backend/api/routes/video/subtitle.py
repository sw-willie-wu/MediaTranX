"""
字幕提取 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.video.subtitle_service import get_subtitle_service
from backend.core.models.base_translator import SUPPORTED_LANGUAGES
from backend.core.models.translategemma import get_translategemma
from backend.core.models.translation import get_translator

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


class WhisperStatusResponse(BaseModel):
    """Whisper 模型狀態回應"""
    available: bool
    model_size: str
    model_downloaded: bool
    device: str
    compute_type: str
    device_name: str


class TranslateGemmaStatusResponse(BaseModel):
    """TranslateGemma 模型狀態回應"""
    available: bool
    model_size: str
    model_downloaded: bool
    device: str
    compute_type: str
    device_name: str


@router.get("/whisper/status", response_model=WhisperStatusResponse)
async def get_whisper_status(model_size: str = "medium"):
    """
    查詢 Whisper 模型狀態

    - **model_size**: 要查詢的模型大小 (預設 medium)
    """
    try:
        service = get_subtitle_service()
        status = service.get_model_status(model_size)
        return WhisperStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translategemma/status", response_model=TranslateGemmaStatusResponse)
async def get_translategemma_status(model_size: str = "4b"):
    """查詢 TranslateGemma 模型狀態"""
    try:
        tg = get_translategemma()
        status = tg.get_model_status(model_size)
        return TranslateGemmaStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translate/status")
async def get_translate_model_status(model_type: str = "translategemma", model_size: str = "4b", quantization: str | None = None):
    """查詢翻譯模型狀態（通用，支援 translategemma 和 qwen3）"""
    try:
        translator = get_translator(model_type)
        status = translator.get_model_status(model_size, quantization)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translategemma/languages")
async def get_translategemma_languages():
    """取得翻譯模型支援的翻譯語言列表"""
    return SUPPORTED_LANGUAGES


class TranslateTestResponse(BaseModel):
    """翻譯測試回應"""
    result: str
    prompt: str


class TranslateTestRequest(BaseModel):
    """翻譯測試請求"""
    text: str = Field(..., description="要翻譯的文字（可以是 SRT 格式）")
    target_language: str = Field(default="zh-TW", description="目標語言")
    source_language: str = Field(default="ja", description="來源語言")
    prompt_style: str = Field(
        default="gemma_chat",
        description="Prompt 風格: gemma_chat, chinese, english, simple"
    )
    model_size: str = Field(
        default="4b",
        description="模型大小: 4b, 12b, 27b"
    )


@router.post("/translategemma/test", response_model=TranslateTestResponse)
async def test_translate(request: TranslateTestRequest):
    """
    測試翻譯 prompt（開發用）

    直接呼叫模型測試翻譯效果，支援多種 prompt 風格
    """
    try:
        tg = get_translategemma()

        # 手動載入模型
        tg._load_model(request.model_size)

        # 語言名稱
        lang_names_zh = {
            "zh-TW": "繁體中文", "zh-CN": "簡體中文", "en": "英文",
            "ja": "日文", "ko": "韓文", "fr": "法文", "de": "德文",
            "es": "西班牙文", "ru": "俄文", "pt": "葡萄牙文", "it": "義大利文",
        }
        lang_names_en = {
            "zh-TW": "Traditional Chinese", "zh-CN": "Simplified Chinese", "en": "English",
            "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German",
            "es": "Spanish", "ru": "Russian", "pt": "Portuguese", "it": "Italian",
        }
        target_zh = lang_names_zh.get(request.target_language, request.target_language)
        target_en = lang_names_en.get(request.target_language, request.target_language)
        source_en = lang_names_en.get(request.source_language, request.source_language)

        # 根據風格選擇 prompt
        if request.prompt_style == "gemma_chat":
            # Gemma 2 chat template 格式 + 保留人名（用中文指示可能更好）
            user_msg = f"""將以下日文字幕翻譯成繁體中文。

翻譯規則：
- 保持 SRT 格式和時間標籤不變
- 使用口語化的翻譯風格
- 【重要】人名保持原文不翻譯，例如：アノン、友理、MyGO 等名字要保留日文原文
- 只輸出翻譯結果

字幕：
{request.text}"""
            prompt = f"<start_of_turn>user\n{user_msg}<end_of_turn>\n<start_of_turn>model\n"
            stop = ["<end_of_turn>"]
        elif request.prompt_style == "chinese":
            # 中文 prompt（你之前在 Ollama 測試成功的版本）
            prompt = (
                f"你是一個專業的影視翻譯員。"
                f"請將以下 SRT 格式的字幕翻譯成{target_zh}，並調整為對應的文法。"
                f"請保持時間標籤不變，翻譯風格偏口語，遇到人名或專有名詞保持原文。"
                f"以下是原始字幕\n{request.text}"
            )
            stop = None
        elif request.prompt_style == "english":
            # 官方英文 prompt
            prompt = (
                f"You are a professional {source_en} to {target_en} translator. "
                f"Translate the following SRT subtitles. Keep timestamps unchanged. "
                f"Output only the translated SRT, no explanations.\n\n{request.text}"
            )
            stop = None
        else:  # simple
            # 極簡 prompt
            prompt = f"Translate to {target_en}:\n{request.text}\n\nTranslation:"
            stop = None

        # 呼叫模型
        output = tg._model(
            prompt,
            max_tokens=len(request.text) * 3,
            temperature=0.1,  # 降低溫度減少幻覺
            echo=False,
            stop=stop,
        )

        result = output["choices"][0]["text"].strip()

        return TranslateTestResponse(result=result, prompt=prompt)
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
