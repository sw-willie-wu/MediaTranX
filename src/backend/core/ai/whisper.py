"""
Whisper 語音辨識模組
封裝 faster-whisper，提供模型管理和語音轉文字功能
模型不打包在 app 中，首次使用時自動下載
"""
import gc
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from backend.core.device import get_device, get_compute_type
from backend.core.paths import get_models_dir
from .model_manager import get_model_manager, SLOT_WHISPER

logger = logging.getLogger(__name__)

# 全域 list：保持已卸載的 CTranslate2 模型物件不被 GC 回收
# CTranslate2 的 C++ 解構子在 Windows 上會觸發 STATUS_STACK_BUFFER_OVERRUN crash
# 透過保持 Python 引用存活來避免解構子執行
_zombie_models: list = []

# 模型存放路徑
_MODELS_DIR = get_models_dir("whisper")

# 支援的模型大小及其對應的 HuggingFace repo
MODEL_SIZES = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

# 各模型大小的預估 VRAM 需求（MB）
MODEL_VRAM_MB = {
    "tiny": 500,
    "base": 700,
    "small": 1500,
    "medium": 3000,
    "large-v3": 5000,
}


@dataclass
class TranscribeSegment:
    """轉錄片段"""
    start: float   # 開始時間（秒）
    end: float     # 結束時間（秒）
    text: str      # 辨識文字


@dataclass
class TranscribeResult:
    """轉錄結果"""
    language: str                    # 偵測到的語言
    language_probability: float      # 語言機率
    segments: list[TranscribeSegment]
    duration: float                  # 音訊總長（秒）


class WhisperWrapper:
    """
    Faster-whisper 封裝類別
    惰性載入：模型在首次轉錄時才載入到記憶體
    """

    def __init__(self):
        self._model = None
        self._current_model_size: Optional[str] = None
        self._lock = threading.RLock()  # RLock: _unload_model 會在 transcribe 的 lock 內重入
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # 註冊卸載回調
        manager = get_model_manager()
        manager.register_unloader(SLOT_WHISPER, self._unload_model)

    def _unload_model(self) -> None:
        """卸載模型，釋放 GPU 記憶體"""
        with self._lock:
            if self._model is not None:
                logger.info("Unloading Whisper model")

                # 用 CTranslate2 的 unload_model() 安全釋放 CUDA 記憶體
                try:
                    if hasattr(self._model, 'model') and hasattr(self._model.model, 'unload_model'):
                        self._model.model.unload_model()
                        logger.info("CTranslate2 model data unloaded (CUDA memory freed)")
                except Exception as e:
                    logger.warning(f"CTranslate2 unload_model failed: {e}")

                # 保持 Python 物件存活，避免 C++ 解構子觸發 crash
                # CTranslate2 的解構子在 Windows 上會導致 0xC0000409
                _zombie_models.append(self._model)

                self._model = None
                self._current_model_size = None
                get_model_manager().mark_unloaded(SLOT_WHISPER)

    def get_model_status(self, model_size: str = "medium") -> dict:
        """查詢模型狀態（僅檢查套件與模型檔，不偵測 GPU）"""
        try:
            import faster_whisper  # noqa: F401
            available = True
        except Exception:
            available = False

        return {
            "available": available,
            "model_size": model_size,
            "model_downloaded": self._is_model_downloaded(model_size),
        }

    def _get_local_model_dir(self, model_size: str) -> Path:
        """取得模型的本地目錄路徑（平面結構，無 symlink）"""
        return _MODELS_DIR / model_size

    def _is_model_downloaded(self, model_size: str) -> bool:
        """檢查模型是否已下載到本地"""
        repo_name = MODEL_SIZES.get(model_size)
        if not repo_name:
            return False

        # 優先檢查平面目錄（local_dir 模式，無 symlink）
        local_dir = self._get_local_model_dir(model_size)
        if local_dir.exists() and (local_dir / "model.bin").exists():
            return True

        # 相容舊版 HuggingFace cache 目錄結構
        cache_dir = _MODELS_DIR / f"models--{repo_name.replace('/', '--')}"
        if cache_dir.exists():
            snapshots = cache_dir / "snapshots"
            if snapshots.exists():
                for snapshot_dir in snapshots.iterdir():
                    if snapshot_dir.is_dir() and any(snapshot_dir.iterdir()):
                        return True
        return False

    def _ensure_model_downloaded(self, model_size: str) -> str:
        """
        確保模型已下載，回傳本地模型路徑

        使用 local_dir 模式下載（直接複製檔案，不需要 Windows symlink 權限）
        """
        local_dir = self._get_local_model_dir(model_size)

        # 已下載到平面目錄
        if local_dir.exists() and (local_dir / "model.bin").exists():
            return str(local_dir)

        # 檢查舊版 cache 目錄是否有模型（相容既有下載）
        repo_name = MODEL_SIZES[model_size]
        cache_dir = _MODELS_DIR / f"models--{repo_name.replace('/', '--')}"
        if cache_dir.exists():
            snapshots = cache_dir / "snapshots"
            if snapshots.exists():
                for snapshot_dir in snapshots.iterdir():
                    if snapshot_dir.is_dir() and (snapshot_dir / "model.bin").exists():
                        return str(snapshot_dir)

        # 下載到平面目錄（無 symlink）
        logger.info(f"Downloading Whisper model: {model_size} to {local_dir}")
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=repo_name,
            local_dir=str(local_dir),
        )
        return str(local_dir)

    def download_only(self, model_size: str, on_progress=None) -> None:
        """只下載模型，不載入記憶體"""
        if model_size not in MODEL_SIZES:
            raise ValueError(f"不支援的模型大小: {model_size}")

        if self._is_model_downloaded(model_size):
            if on_progress:
                on_progress(1.0, "模型已下載")
            return

        _SIZE_MB = {"tiny": 150, "base": 300, "small": 500, "medium": 1500, "large-v3": 3000}
        size_mb = _SIZE_MB.get(model_size, 1500)
        size_label = f"~{size_mb / 1000:.1f} GB" if size_mb >= 1000 else f"~{size_mb} MB"

        local_dir = self._get_local_model_dir(model_size)
        repo_name = MODEL_SIZES[model_size]

        logger.info(f"Downloading Whisper model: {model_size} to {local_dir}")
        if on_progress:
            on_progress(0.0, f"開始下載 Whisper {model_size} ({size_label})...")

        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=repo_name,
            local_dir=str(local_dir),
        )

        if on_progress:
            on_progress(1.0, "模型下載完成")

    def _load_model(self, model_size: str) -> None:
        """
        載入或下載模型

        Args:
            model_size: 模型大小 (tiny, base, small, medium, large-v3)
        """
        if self._model is not None and self._current_model_size == model_size:
            return

        if model_size not in MODEL_SIZES:
            raise ValueError(f"不支援的模型大小: {model_size}，可選: {list(MODEL_SIZES.keys())}")

        from faster_whisper import WhisperModel

        device = get_device()
        compute_type = get_compute_type()

        # 確保模型已下載（使用 local_dir 模式，避免 Windows symlink 問題）
        model_path = self._ensure_model_downloaded(model_size)

        logger.info(
            f"Loading Whisper model: {model_size} from {model_path} "
            f"(device={device}, compute_type={compute_type})"
        )

        # 傳入本地路徑而非 model_size 字串，避免再次觸發 HF cache 下載
        try:
            self._model = WhisperModel(
                model_path,
                device=device,
                compute_type=compute_type,
            )
        except Exception as e:
            if device != "cpu":
                logger.warning(
                    f"Failed to load model on {device}: {e}. "
                    f"Falling back to CPU (int8)."
                )
                device = "cpu"
                compute_type = "int8"
                self._model = WhisperModel(
                    model_path,
                    device=device,
                    compute_type=compute_type,
                )
            else:
                raise

        self._current_model_size = model_size

        logger.info(f"Whisper model loaded: {model_size} (device={device})")

    def transcribe(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model_size: str = "medium",
        on_progress: Optional[Callable[[float, str], None]] = None,
        # 進階分句參數
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 500,
        vad_threshold: float = 0.5,
    ) -> TranscribeResult:
        """
        轉錄音訊

        Args:
            audio_path: 音訊檔案路徑
            language: 語言代碼 (None 表示自動偵測)
            model_size: 模型大小
            on_progress: 進度回調 (percent 0.0~1.0, message)
            word_timestamps: 啟用詞級時間戳（有助於更精確分句）
            condition_on_previous_text: 是否根據前文調整辨識（False 可避免句子合併）
            min_silence_duration_ms: 最小靜音時長（毫秒），低於此值的停頓不會分句
            vad_threshold: VAD 門檻值 (0-1)，越低越敏感

        Returns:
            TranscribeResult
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音訊檔案不存在: {audio_path}")

        # 使用鎖確保同一時間只有一個轉錄任務（避免 GPU 記憶體競爭導致崩潰）
        with self._lock:
            manager = get_model_manager()
            vram_needed = MODEL_VRAM_MB.get(model_size, 3000)
            manager.acquire(SLOT_WHISPER, required_vram_mb=vram_needed)

            try:
                # 載入模型（首次使用會自動下載）
                if on_progress:
                    on_progress(0.0, "載入語音辨識模型...")
                self._load_model(model_size)

                if on_progress:
                    on_progress(0.05, "開始語音辨識...")

                # 執行轉錄
                segments_gen, info = self._model.transcribe(
                    str(audio_path),
                    language=language,
                    beam_size=5,
                    word_timestamps=word_timestamps,
                    condition_on_previous_text=condition_on_previous_text,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=min_silence_duration_ms,
                        threshold=vad_threshold,
                    ),
                )

                duration = info.duration
                detected_language = info.language
                language_probability = info.language_probability

                logger.info(
                    f"Detected language: {detected_language} "
                    f"(probability: {language_probability:.2f}), "
                    f"duration: {duration:.1f}s"
                )

                # 收集 segments 並追蹤進度
                segments: list[TranscribeSegment] = []
                for segment in segments_gen:
                    segments.append(TranscribeSegment(
                        start=segment.start,
                        end=segment.end,
                        text=segment.text.strip(),
                    ))

                    # 根據已處理的時間計算進度
                    if on_progress and duration > 0:
                        progress = min(segment.end / duration, 1.0)
                        on_progress(
                            progress,
                            f"辨識中... {progress:.0%} ({segment.end:.1f}s / {duration:.1f}s)"
                        )

                if on_progress:
                    on_progress(1.0, "語音辨識完成")

                return TranscribeResult(
                    language=detected_language,
                    language_probability=language_probability,
                    segments=segments,
                    duration=duration,
                )

            finally:
                self._unload_model()


# 單例
_whisper: Optional[WhisperWrapper] = None


def get_whisper() -> WhisperWrapper:
    """取得 WhisperWrapper 單例"""
    global _whisper
    if _whisper is None:
        _whisper = WhisperWrapper()
    return _whisper
