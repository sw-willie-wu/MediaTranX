"""
Whisper 語音辨識模組
封裝 faster-whisper，提供模型管理和語音轉文字功能
模型不打包在 app 中，首次使用時自動下載
"""
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from backend.core.device import get_device, get_compute_type, get_device_info

logger = logging.getLogger(__name__)

# 模型存放路徑（專案根目錄下）
_MODELS_DIR = Path(__file__).parent.parent.parent.parent / "models" / "whisper"

# 支援的模型大小及其對應的 HuggingFace repo
MODEL_SIZES = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
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
        self._lock = threading.Lock()  # 確保同一時間只有一個轉錄任務使用 GPU
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)

    def get_model_status(self, model_size: str = "medium") -> dict:
        """
        查詢模型狀態

        Returns:
            dict: available, model_size, model_downloaded, device, compute_type
        """
        try:
            import faster_whisper  # noqa: F401
            available = True
        except ImportError:
            available = False

        info = get_device_info()
        return {
            "available": available,
            "model_size": model_size,
            "model_downloaded": self._is_model_downloaded(model_size),
            "device": info["device"],
            "compute_type": info["compute_type"],
            "device_name": info["device_name"],
        }

    def _is_model_downloaded(self, model_size: str) -> bool:
        """檢查模型是否已下載到本地"""
        repo_name = MODEL_SIZES.get(model_size)
        if not repo_name:
            return False

        # faster-whisper 使用 huggingface_hub 下載，
        # 快取目錄結構為: models/whisper/models--Systran--faster-whisper-{size}/
        cache_dir = _MODELS_DIR / f"models--{repo_name.replace('/', '--')}"
        if cache_dir.exists():
            # 確認 snapshots 資料夾中有實際模型檔
            snapshots = cache_dir / "snapshots"
            if snapshots.exists():
                for snapshot_dir in snapshots.iterdir():
                    if snapshot_dir.is_dir() and any(snapshot_dir.iterdir()):
                        return True
        return False

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

        logger.info(
            f"Loading Whisper model: {model_size} "
            f"(device={device}, compute_type={compute_type})"
        )

        # faster-whisper 會自動從 HuggingFace 下載模型到 download_root
        # 如果 CUDA 載入失敗（缺少 runtime 函式庫），自動 fallback 到 CPU
        try:
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                download_root=str(_MODELS_DIR),
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
                    model_size,
                    device=device,
                    compute_type=compute_type,
                    download_root=str(_MODELS_DIR),
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
    ) -> TranscribeResult:
        """
        轉錄音訊

        Args:
            audio_path: 音訊檔案路徑
            language: 語言代碼 (None 表示自動偵測)
            model_size: 模型大小
            on_progress: 進度回調 (percent 0.0~1.0, message)

        Returns:
            TranscribeResult
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音訊檔案不存在: {audio_path}")

        # 使用鎖確保同一時間只有一個轉錄任務（避免 GPU 記憶體競爭導致崩潰）
        with self._lock:
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
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
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


# 單例
_whisper: Optional[WhisperWrapper] = None


def get_whisper() -> WhisperWrapper:
    """取得 WhisperWrapper 單例"""
    global _whisper
    if _whisper is None:
        _whisper = WhisperWrapper()
    return _whisper
