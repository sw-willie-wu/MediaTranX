"""
翻譯模型基礎類別
將 TranslateGemma 和 Qwen3 的共用邏輯抽出，子類只需覆寫 prompt 建構方法
"""
import gc
import glob
import logging
import os
import re
import sys
import threading
import time
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from backend.core.device import has_nvidia_gpu
from .model_manager import get_model_manager

logger = logging.getLogger(__name__)

# === 共用常數 ===

# Whisper 語言代碼 (ISO 639-1) → BCP 47
WHISPER_TO_BCP47 = {
    "zh": "zh-CN",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "ru": "ru",
    "pt": "pt",
    "it": "it",
    "th": "th",
    "vi": "vi",
    "ar": "ar",
    "hi": "hi",
    "id": "id",
    "nl": "nl",
    "pl": "pl",
    "sv": "sv",
    "tr": "tr",
    "uk": "uk",
}

# 支援的目標語言列表（供 API 回傳）
SUPPORTED_LANGUAGES = [
    {"code": "zh-TW", "name": "繁體中文"},
    {"code": "zh-CN", "name": "簡體中文"},
    {"code": "en", "name": "英文"},
    {"code": "ja", "name": "日文"},
    {"code": "ko", "name": "韓文"},
    {"code": "fr", "name": "法文"},
    {"code": "de", "name": "德文"},
    {"code": "es", "name": "西班牙文"},
    {"code": "ru", "name": "俄文"},
    {"code": "pt", "name": "葡萄牙文"},
    {"code": "it", "name": "義大利文"},
    {"code": "th", "name": "泰文"},
    {"code": "vi", "name": "越南文"},
    {"code": "ar", "name": "阿拉伯文"},
    {"code": "hi", "name": "印地文"},
    {"code": "id", "name": "印尼文"},
    {"code": "nl", "name": "荷蘭文"},
    {"code": "pl", "name": "波蘭文"},
    {"code": "sv", "name": "瑞典文"},
    {"code": "tr", "name": "土耳其文"},
    {"code": "uk", "name": "烏克蘭文"},
]

# 語言名稱對照（英文）
LANG_NAMES_EN = {
    "en": "English", "zh-TW": "Traditional Chinese", "zh-CN": "Simplified Chinese",
    "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German",
    "es": "Spanish", "ru": "Russian", "pt": "Portuguese", "it": "Italian",
    "th": "Thai", "vi": "Vietnamese", "ar": "Arabic", "hi": "Hindi",
    "id": "Indonesian", "nl": "Dutch", "pl": "Polish", "sv": "Swedish",
    "tr": "Turkish", "uk": "Ukrainian",
}

# 語言名稱對照（中文）
LANG_NAMES_ZH = {
    "zh-TW": "繁體中文", "zh-CN": "簡體中文", "en": "英文",
    "ja": "日文", "ko": "韓文", "fr": "法文", "de": "德文",
    "es": "西班牙文", "ru": "俄文", "pt": "葡萄牙文", "it": "義大利文",
    "th": "泰文", "vi": "越南文", "ar": "阿拉伯文", "hi": "印地文",
    "id": "印尼文", "nl": "荷蘭文", "pl": "波蘭文", "sv": "瑞典文",
    "tr": "土耳其文", "uk": "烏克蘭文",
}

# 翻譯風格說明
STYLE_INSTRUCTIONS = {
    "colloquial": "使用口語化的翻譯風格",
    "formal": "使用正式、書面的翻譯風格",
    "literal": "盡量直譯，保持原文結構",
}


@dataclass
class TranslateResult:
    """翻譯結果"""
    source_language: str
    target_language: str
    text: str
    model_size: str


def _setup_cuda_dll_path():
    """
    Windows 上 llama-cpp-python CUDA 版需要 NVIDIA 的 DLL（cublas、cudart 等）。
    這些 DLL 由 pip 安裝在 site-packages/nvidia/*/bin/ 下，
    但不在系統 PATH 中，需要手動加入。

    frozen 模式下跳過：CUDA 由使用者系統環境提供。
    """
    if sys.platform != "win32":
        return
    if getattr(sys, 'frozen', False):
        return
    site = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
    if not os.path.isdir(site):
        return
    for bin_dir in glob.glob(os.path.join(site, "*", "bin")):
        if bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


_setup_cuda_dll_path()


def _split_by_sentences(text: str, max_chars: int) -> list[str]:
    """按句子邊界拆分文字"""
    sentences = re.split(r'(?<=[。！？.!?\n])\s*', text)
    chunks = []
    current = ""

    for sent in sentences:
        if not sent:
            continue
        if not current:
            current = sent
        elif len(current) + len(sent) + 1 <= max_chars:
            current += " " + sent
        else:
            chunks.append(current)
            current = sent

    if current:
        chunks.append(current)

    return chunks


class BaseTranslator:
    """
    翻譯模型共用基礎類別

    子類必須覆寫：
    - CLASS ATTRS: MODEL_VARIANTS, DEFAULT_QUANT, SLOT, MODEL_NAME, _MODELS_DIR, etc.
    - METHODS: _generate_translation(), _generate_srt_translation()
    """

    # === 子類必須覆寫的 class attrs ===
    MODEL_VARIANTS: dict = {}       # {"size": {"quant": {"repo_id":..., "filename":..., "size_mb":...}}}
    DEFAULT_QUANT: dict = {}        # {"size": "Q4_K_M"}
    SLOT: str = ""                  # ModelManager slot 名稱
    MODEL_NAME: str = ""            # 顯示名稱（用於 log）
    _MODELS_DIR: Path = Path(".")   # 模型下載目錄
    _MODEL_LAYERS: dict = {}        # {"size": int}
    _VRAM_OVERHEAD_MB: dict = {}    # {"size": int}
    _MODEL_N_CTX: dict = {}         # {"size": int}

    def __init__(self):
        self._model = None
        self._current_model_size: Optional[str] = None
        self._current_quantization: Optional[str] = None
        self._lock = threading.RLock()
        self._MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # 註冊卸載回調
        manager = get_model_manager()
        manager.register_unloader(self.SLOT, self._unload_model)

    def _unload_model(self) -> None:
        """卸載模型，釋放記憶體"""
        with self._lock:
            if self._model is not None:
                logger.info(f"Unloading {self.MODEL_NAME} model")
                model = self._model
                self._model = None
                self._current_model_size = None
                self._current_quantization = None
                del model
                gc.collect()
                get_model_manager().mark_unloaded(self.SLOT)

    def _get_variant(self, model_size: str, quantization: Optional[str] = None) -> dict:
        """取得指定模型大小和量化的變體資訊"""
        quants = self.MODEL_VARIANTS.get(model_size)
        if not quants:
            raise ValueError(
                f"不支援的模型大小: {model_size}，可選: {list(self.MODEL_VARIANTS.keys())}"
            )
        quant = quantization or self.DEFAULT_QUANT.get(model_size, "Q4_K_M")
        variant = quants.get(quant)
        if not variant:
            raise ValueError(
                f"不支援的量化: {quant}，可選: {list(quants.keys())}"
            )
        return variant

    def _get_model_file_mb(self, model_size: str, quantization: Optional[str] = None) -> int:
        """取得模型檔案大小（MB）"""
        variant = self._get_variant(model_size, quantization)
        return variant["size_mb"]

    def get_model_status(self, model_size: str = "4b", quantization: Optional[str] = None) -> dict:
        """查詢模型狀態（僅檢查套件與模型檔，不偵測 GPU）"""
        available = True

        try:
            import llama_cpp  # noqa: F401
        except Exception:
            available = False

        return {
            "available": available,
            "model_size": model_size,
            "model_downloaded": self._is_model_downloaded(model_size, quantization),
        }

    def _is_model_downloaded(self, model_size: str, quantization: Optional[str] = None) -> bool:
        """檢查模型是否已下載到本地"""
        try:
            variant = self._get_variant(model_size, quantization)
        except ValueError:
            return False

        try:
            from huggingface_hub import try_to_load_from_cache
            result = try_to_load_from_cache(
                repo_id=variant["repo_id"],
                filename=variant["filename"],
                cache_dir=str(self._MODELS_DIR),
            )
            return result is not None and isinstance(result, str)
        except Exception:
            # Fallback: 直接掃描目錄
            repo_dir = self._MODELS_DIR / f"models--{variant['repo_id'].replace('/', '--')}"
            if repo_dir.exists():
                snapshots = repo_dir / "snapshots"
                if snapshots.exists():
                    for snapshot_dir in snapshots.iterdir():
                        if snapshot_dir.is_dir():
                            gguf_file = snapshot_dir / variant["filename"]
                            if gguf_file.exists():
                                return True
            return False

    def _download_model(self, model_size: str, quantization: Optional[str] = None, on_progress=None) -> str:
        """下載模型，回傳本地路徑"""
        variant = self._get_variant(model_size, quantization)

        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            raise RuntimeError("需要 huggingface-hub 套件來下載模型")

        # 檢查是否需要下載
        needs_download = not self._is_model_downloaded(model_size, quantization)

        if needs_download:
            size_mb = variant["size_mb"]
            size_label = f"~{size_mb / 1000:.1f} GB" if size_mb >= 1000 else f"~{size_mb} MB"
            logger.info(f"開始下載 {self.MODEL_NAME} 模型 ({size_label})，首次下載可能需要較長時間...")

            if on_progress:
                on_progress(0.0, f"首次使用，正在下載模型 ({size_label})，請稍候...")

        model_path = hf_hub_download(
            repo_id=variant["repo_id"],
            filename=variant["filename"],
            cache_dir=str(self._MODELS_DIR),
        )

        if needs_download:
            logger.info(f"{self.MODEL_NAME} 模型下載完成")
            if on_progress:
                on_progress(1.0, "模型下載完成")

        return model_path

    @staticmethod
    def _get_free_vram_mb() -> int:
        """透過 nvidia-smi 查詢可用 VRAM（MB），失敗回傳 0"""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split("\n")[0])
        except Exception:
            pass
        return 0

    def _load_model(self, model_size: str, quantization: Optional[str] = None, on_progress=None) -> None:
        """載入或下載模型，自動根據 VRAM 決定 GPU offload 策略"""
        quant = quantization or self.DEFAULT_QUANT.get(model_size, "Q4_K_M")

        if (self._model is not None
                and self._current_model_size == model_size
                and self._current_quantization == quant):
            return

        # 驗證模型大小
        self._get_variant(model_size, quant)

        # 若大小/量化不同，先卸載舊模型，並重新讓 ModelManager 評估 VRAM
        if self._model is not None:
            self._unload_model()
            # 重新 acquire：讓 ModelManager 重新檢查 VRAM 並 evict 其他模型
            manager = get_model_manager()
            file_mb = self._get_model_file_mb(model_size, quant)
            overhead = self._VRAM_OVERHEAD_MB.get(model_size, 800)
            manager.acquire(self.SLOT, required_vram_mb=file_mb + overhead)

        try:
            from llama_cpp import Llama
        except ImportError:
            raise RuntimeError(
                "翻譯功能需要安裝 llama-cpp-python，請先安裝翻譯功能"
            )

        # 下載模型（如果尚未下載）
        model_path = self._download_model(model_size, quant, on_progress)

        # 根據可用 VRAM 決定 GPU offload 策略
        gpu = has_nvidia_gpu()
        n_gpu_layers = 0
        total_layers = self._MODEL_LAYERS.get(model_size, 26)
        model_file_mb = self._get_model_file_mb(model_size, quant)
        per_layer_mb = model_file_mb / total_layers

        if gpu:
            # 多次檢查 VRAM（CUDA 記憶體釋放可能有延遲）
            vram_readings = []
            for attempt in range(5):
                free_vram = self._get_free_vram_mb()
                vram_readings.append(free_vram)
                if free_vram >= model_file_mb:
                    break
                if attempt < 4:
                    time.sleep(1.0)

            best_free_vram = max(vram_readings)
            logger.info(f"VRAM readings: {vram_readings}, using best: {best_free_vram}MB")

            free_vram = best_free_vram
            overhead = self._VRAM_OVERHEAD_MB.get(model_size, 800)
            usable_vram = free_vram - overhead

            if usable_vram >= model_file_mb:
                # 全部 layer offload 到 GPU（KV cache 也跟著 layer 一起在 GPU 上）
                # 注意：不用 -1，因為 -1 額外把 embedding/output/scratch 也放 GPU，
                # 可能導致 VRAM overflow 的 C-level crash（無法用 try/except 捕捉）
                n_gpu_layers = total_layers
                logger.info(
                    f"VRAM sufficient ({free_vram}MB free, {model_file_mb}MB model + "
                    f"{overhead}MB overhead) — all {total_layers} layers + KV cache on GPU"
                )
            elif usable_vram > per_layer_mb:
                n_gpu_layers = min(int(usable_vram / per_layer_mb), total_layers)
                logger.info(
                    f"Partial offload: {n_gpu_layers}/{total_layers} layers to GPU "
                    f"({free_vram}MB free, usable {usable_vram}MB, "
                    f"using ~{int(n_gpu_layers * per_layer_mb)}MB for {n_gpu_layers}/{total_layers} layers)"
                )
            else:
                n_gpu_layers = max(4, int(free_vram / per_layer_mb / 2))
                logger.info(
                    f"VRAM low ({free_vram}MB free) — trying {n_gpu_layers} layers anyway"
                )

        n_ctx = self._MODEL_N_CTX.get(model_size, 2048)
        logger.info(
            f"Loading {self.MODEL_NAME} GGUF: {model_size} {quant} "
            f"(n_gpu_layers={n_gpu_layers}, n_ctx={n_ctx})"
        )

        # 漸進式載入：如果失敗就減少 GPU 層數重試
        min_n_ctx = 256
        while True:
            try:
                self._model = Llama(
                    model_path=model_path,
                    n_ctx=n_ctx,
                    n_gpu_layers=n_gpu_layers,
                    verbose=False,
                )
                break
            except Exception as e:
                error_msg = str(e).lower()
                # "failed to create llama_context" 通常也是記憶體不足
                is_memory_error = any(x in error_msg for x in [
                    "memory", "cuda", "gpu", "alloc", "context",
                ])

                if n_gpu_layers > 0 and is_memory_error:
                    n_gpu_layers = max(0, n_gpu_layers - 4)
                    logger.warning(
                        f"GPU memory error, retrying with {n_gpu_layers} layers: {e}"
                    )
                    gc.collect()
                elif n_gpu_layers > 0:
                    logger.warning(f"GPU load failed, falling back to CPU: {e}")
                    n_gpu_layers = 0
                    gc.collect()
                elif is_memory_error and n_ctx > min_n_ctx:
                    # CPU 也失敗時，嘗試減少 context 長度
                    n_ctx = max(min_n_ctx, n_ctx // 2)
                    logger.warning(
                        f"CPU load failed, retrying with reduced n_ctx={n_ctx}: {e}"
                    )
                    gc.collect()
                else:
                    raise

        self._current_model_size = model_size
        self._current_quantization = quant
        logger.info(f"{self.MODEL_NAME} model loaded: {model_size} (GGUF {quant})")

    @staticmethod
    def _format_glossary(glossary: Optional[dict[str, str]]) -> str:
        """將 glossary dict 格式化為 prompt 段落"""
        if not glossary:
            return ""
        lines = "\n".join(f"- {src} → {tgt}" for src, tgt in glossary.items())
        return (
            f"\n專有名詞對照表（翻譯時請嚴格依照此表，"
            f"名稱在字幕中可能以片假名、平假名、簡稱等不同形式出現，請自行對應）：\n{lines}\n"
        )

    def _format_srt_time(self, seconds: float) -> str:
        """將秒數格式化為 SRT 時間格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _segments_to_srt(self, segments: list[dict], start_index: int = 1) -> str:
        """將 segments 轉換為 SRT 格式字串"""
        lines = []
        for i, seg in enumerate(segments, start_index):
            start_time = self._format_srt_time(seg["start"])
            end_time = self._format_srt_time(seg["end"])
            lines.append(f"{i}")
            lines.append(f"{start_time} --> {end_time}")
            lines.append(seg["text"])
            lines.append("")
        return "\n".join(lines)

    def _parse_srt_response(self, srt_text: str, original_segments: list[dict]) -> list[dict]:
        """解析翻譯後的 SRT 格式，回傳 segments"""
        pattern = r'(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n([\s\S]*?)(?=\n\n\d+\s*\n|\n*$)'
        matches = re.findall(pattern, srt_text.strip() + "\n\n")

        translated = []
        for i, orig_seg in enumerate(original_segments):
            if i < len(matches):
                _, _, _, text = matches[i]
                cleaned = text.strip()
                translated.append({
                    "start": orig_seg["start"],
                    "end": orig_seg["end"],
                    "text": cleaned if cleaned else orig_seg["text"],
                })
            else:
                translated.append(orig_seg)

        return translated

    # === 子類必須覆寫的方法 ===

    @abstractmethod
    def _generate_translation(
        self, text: str, source_lang: str, target_lang: str,
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
        """翻譯一般文字（子類覆寫以套用不同 prompt 格式）"""
        ...

    @abstractmethod
    def _generate_srt_translation(
        self,
        srt_text: str,
        source_lang: str,
        target_lang: str,
        keep_names: bool = True,
        style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
        """翻譯 SRT 字幕（子類覆寫以套用不同 prompt 格式）"""
        ...

    # === 共用翻譯流程 ===

    def translate_segments(
        self,
        segments: list[dict],
        source_lang: str,
        target_lang: str,
        model_size: str = "4b",
        quantization: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        batch_size: int = 5,
        keep_names: bool = True,
        style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
    ) -> list[dict]:
        """批次翻譯字幕 segments（使用 SRT 格式）"""
        src = WHISPER_TO_BCP47.get(source_lang, source_lang)

        with self._lock:
            manager = get_model_manager()
            file_mb = self._get_model_file_mb(model_size, quantization)
            overhead = self._VRAM_OVERHEAD_MB.get(model_size, 800)
            manager.acquire(self.SLOT, required_vram_mb=file_mb + overhead)

            try:
                def _load_progress(p, msg):
                    if on_progress:
                        on_progress(p * 0.05, msg)

                if on_progress:
                    on_progress(0.0, f"載入 {self.MODEL_NAME} 翻譯模型...")
                self._load_model(model_size, quantization, _load_progress)

                if on_progress:
                    on_progress(0.05, "開始翻譯字幕...")

                total = len(segments)
                translated = []
                num_batches = (total + batch_size - 1) // batch_size

                for batch_idx in range(num_batches):
                    start_idx = batch_idx * batch_size
                    end_idx = min(start_idx + batch_size, total)
                    batch_segments = segments[start_idx:end_idx]

                    srt_text = self._segments_to_srt(batch_segments, start_index=start_idx + 1)

                    translated_srt = self._generate_srt_translation(
                        srt_text, src, target_lang,
                        keep_names=keep_names,
                        style=style,
                        glossary=glossary,
                    )

                    batch_translated = self._parse_srt_response(translated_srt, batch_segments)
                    translated.extend(batch_translated)

                    if on_progress and num_batches > 0:
                        progress = min((batch_idx + 1) / num_batches, 1.0)
                        on_progress(
                            0.05 + progress * 0.95,
                            f"翻譯中... {end_idx}/{total} 段"
                        )

                if on_progress:
                    on_progress(1.0, "字幕翻譯完成")

                return translated

            finally:
                self._unload_model()

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        model_size: str = "4b",
        quantization: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        glossary: Optional[dict[str, str]] = None,
    ) -> TranslateResult:
        """長文翻譯，自動切 chunk"""
        with self._lock:
            manager = get_model_manager()
            file_mb = self._get_model_file_mb(model_size, quantization)
            overhead = self._VRAM_OVERHEAD_MB.get(model_size, 1000)
            manager.acquire(self.SLOT, required_vram_mb=file_mb + overhead)

            try:
                def _load_progress(p, msg):
                    if on_progress:
                        on_progress(p * 0.05, msg)

                if on_progress:
                    on_progress(0.0, f"載入 {self.MODEL_NAME} 翻譯模型...")
                self._load_model(model_size, quantization, _load_progress)

                if on_progress:
                    on_progress(0.05, "開始翻譯...")

                chunks = self._split_text(text, max_chars=1500)
                total = len(chunks)
                translated_chunks = []

                for i, chunk in enumerate(chunks):
                    result_text = self._generate_translation(chunk, source_lang, target_lang, glossary=glossary)
                    translated_chunks.append(result_text)

                    if on_progress and total > 0:
                        progress = min((i + 1) / total, 1.0)
                        on_progress(
                            0.05 + progress * 0.95,
                            f"翻譯中... {progress:.0%} ({i + 1}/{total} 段)"
                        )

                full_text = "\n\n".join(translated_chunks)

                if on_progress:
                    on_progress(1.0, "翻譯完成")

                return TranslateResult(
                    source_language=source_lang,
                    target_language=target_lang,
                    text=full_text,
                    model_size=model_size,
                )

            finally:
                self._unload_model()

    @staticmethod
    def _split_text(text: str, max_chars: int = 1500) -> list[str]:
        """將長文切割成適合翻譯的 chunks"""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            if not current_chunk:
                current_chunk = para
            elif len(current_chunk) + len(para) + 2 <= max_chars:
                current_chunk += "\n\n" + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(para) > max_chars:
                    chunks.extend(_split_by_sentences(para, max_chars))
                    current_chunk = ""
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks
