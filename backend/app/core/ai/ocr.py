"""
VLM OCR 封裝器（LlamaServerRuntime 版）
使用視覺語言模型（Qwen3-VL、InternVL2.5、Gemma3）辨識圖片中的文字。
"""
import base64
import logging
from pathlib import Path
from typing import Optional, Callable

from app.core.ai.registry import SLOT_VLM
from app.core.ai.base.llama_server_runtime import LlamaServerRuntime
from app.core.ai.model_manager import get_model_manager

logger = logging.getLogger(__name__)

# 預設模型 ID（使用者可選擇）
DEFAULT_VLM_MODEL = "qwen3vl"

# OCR prompt — 純文字模式
_IGNORE_VISUAL = (
    "Ignore QR codes, barcodes, logos, icons, and any purely visual/graphical elements — "
    "extract only human-readable text."
)

# OCR prompt — 純文字模式
_OCR_SYSTEM_TXT = (
    "You are an OCR assistant. Extract all text from the image exactly as it appears. "
    "Output only the extracted text, preserving line breaks and layout as much as possible. "
    f"{_IGNORE_VISUAL} "
    "Do not add explanations, commentary, or any formatting markers."
)

_OCR_USER_TXT = (
    "Please extract all human-readable text from this image. "
    "Output only the plain text content, nothing else."
)

# OCR prompt — Markdown 模式
_OCR_SYSTEM_MD = (
    "You are an OCR assistant. Extract all text from the image and format the output in Markdown. "
    f"{_IGNORE_VISUAL} "
    "Rules:\n"
    "- If the image contains a table, represent it as a Markdown table (| col | col | with --- separator row).\n"
    "- Use # headings for titles or section headers you can identify.\n"
    "- Preserve paragraph breaks with blank lines.\n"
    "- Output only the extracted content in Markdown format, no explanations or commentary."
)

_OCR_USER_MD = (
    "Please extract all human-readable text from this image and format it in Markdown. "
    "Represent any tables as Markdown tables. Output only the Markdown content."
)


class VlmOcrWrapper:
    """
    VLM OCR 封裝類別（單例）

    使用 LlamaServerRuntime 啟動 llama-server subprocess，
    透過 /v1/chat/completions 的 image_url 欄位傳入 base64 圖片。
    """
    _instance: Optional["VlmOcrWrapper"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._runtime = LlamaServerRuntime(SLOT_VLM)
        self._initialized = True

    @staticmethod
    def is_available() -> bool:
        """檢查 llama-server 二進位是否存在"""
        return get_model_manager().is_llama_ready()

    def get_status(self, model_id: str = DEFAULT_VLM_MODEL, size: str = "4b", quantization: Optional[str] = None) -> dict:
        """查詢可用狀態與模型下載狀態"""
        available = self.is_available()
        variant = f"{size}:{quantization}" if quantization else size
        model_downloaded = (
            get_model_manager().get_model_path(model_id, variant) is not None
        )
        return {
            "available": available,
            "model_id": model_id,
            "size": size,
            "model_downloaded": model_downloaded,
        }

    def recognize(
        self,
        image_path: str,
        model_id: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
        format: str = "md",
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> str:
        """
        辨識圖片中的文字，回傳原始文字字串。

        Args:
            image_path: 圖片路徑
            model_id: VLM 模型 ID（qwen3vl / internvl2.5 / gemma3）
            size: 模型大小（1b / 2b / 4b / 8b / 12b）
            quantization: 量化格式（Q4_K_M / Q8_0）
            on_progress: 進度回調

        Returns:
            辨識出的文字
        """
        variant = f"{size}:{quantization}" if quantization else size

        # 讀取並 base64 編碼圖片
        image_bytes = Path(image_path).read_bytes()
        ext = Path(image_path).suffix.lower().lstrip(".")
        mime = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp", "gif": "image/gif",
        }.get(ext, "image/jpeg")
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"

        sys_prompt  = _OCR_SYSTEM_MD  if format == "md" else _OCR_SYSTEM_TXT
        user_prompt = _OCR_USER_MD    if format == "md" else _OCR_USER_TXT

        messages = [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]

        with self._runtime.acquire(model_id, variant, on_progress) as rt:
            return rt.chat(messages=messages, max_tokens=4096, temperature=0.0)


# 單例存取
_instance: Optional[VlmOcrWrapper] = None


def get_vlm_ocr() -> VlmOcrWrapper:
    global _instance
    if _instance is None:
        _instance = VlmOcrWrapper()
    return _instance
