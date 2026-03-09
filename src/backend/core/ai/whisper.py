"""
Whisper 語音辨識模組 (Three-Layer Architecture V3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
重構：繼承 BINRuntime，移除冗餘載入邏輯，保留轉錄業務邏輯
⚠️ Windows 崩潰防護機制由 BINRuntime 統一管理
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .base import BINRuntime
from .registry import SLOT_WHISPER, FORMAT_BIN, MODELS_REGISTRY

logger = logging.getLogger(__name__)

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


class WhisperWrapper(BINRuntime):
    """
    Whisper 語音辨識封裝（繼承 BINRuntime）
    
    職責：
    1. 轉錄邏輯（語音 → 文字）
    2. 進度計算與分句處理
    3. ⚠️ Windows 崩潰防護由 BINRuntime 統一處理
    """
    
    def __init__(self):
        super().__init__(slot=SLOT_WHISPER)
        logger.info("WhisperWrapper initialized (BINRuntime)")
    
    def get_model_status(self, model_size: str = "medium") -> dict:
        """查詢模型狀態"""
        model_path = self._manager.get_model_path("whisper", model_size)
        
        from backend.core.paths import get_base_data_dir
        venv_fw = get_base_data_dir() / ".venv" / "Lib" / "site-packages" / "faster_whisper"
        available = venv_fw.is_dir()

        return {
            "available": available,
            "model_size": model_size,
            "model_downloaded": model_path is not None,
        }

    async def download_only(self, model_size: str, on_progress=None) -> None:
        """只下載模型，不載入記憶體"""
        await self._manager.download_model("whisper", model_size, on_progress=on_progress)

    def transcribe(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model_size: str = "medium",
        on_progress: Optional[Callable[[float, str], None]] = None,
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 500,
        vad_threshold: float = 0.5,
    ) -> TranscribeResult:
        """
        轉錄音訊
        
        Args:
            audio_path: 音訊檔案路徑
            language: 指定語言（None 為自動偵測）
            model_size: 模型大小（tiny/base/small/medium/large-v3）
            on_progress: 進度回調
            word_timestamps: 是否生成單字級時間戳
            condition_on_previous_text: 是否使用前文條件
            min_silence_duration_ms: VAD 最小靜音時長
            vad_threshold: VAD 閾值
            
        Returns:
            TranscribeResult
        """
        audio_path = Path(audio_path)
        
        # 獲取 VRAM 需求
        size_config = MODELS_REGISTRY[FORMAT_BIN]["whisper"]["variants"].get(model_size)
        if not size_config:
            raise ValueError(f"Unknown Whisper model size: {model_size}")
        
        vram_needed = size_config["vram_mb"]
        self._manager.acquire(SLOT_WHISPER, required_vram_mb=vram_needed)
        
        try:
            # 使用 BINRuntime 的 acquire() 載入模型
            if on_progress:
                on_progress(0.0, "載入語音辨識模型...")
            
            with self.acquire(
                model_id="whisper",
                variant=model_size,
                on_progress=lambda p, m: on_progress(p * 0.05, m) if on_progress else None
            ) as model:
                if on_progress:
                    on_progress(0.05, "開始語音辨識...")

                # 執行轉錄
                segments_gen, info = model.transcribe(
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

                # 收集分句結果
                duration = info.duration
                segments: list[TranscribeSegment] = []
                for segment in segments_gen:
                    segments.append(TranscribeSegment(
                        start=segment.start,
                        end=segment.end,
                        text=segment.text.strip(),
                    ))
                    if on_progress and duration > 0:
                        progress = 0.05 + (segment.end / duration) * 0.95
                        on_progress(min(progress, 1.0), f"辨識中... {progress:.0%}")

                if on_progress:
                    on_progress(1.0, "語音辨識完成")

                return TranscribeResult(
                    language=info.language,
                    language_probability=info.language_probability,
                    segments=segments,
                    duration=duration,
                )
        finally:
            # 卸載模型釋放 VRAM
            self._unload_model()


# ═══════════════════════════════════════════════════════════
# 單例工廠函數（向後兼容）
# ═══════════════════════════════════════════════════════════
_whisper: Optional[WhisperWrapper] = None

def get_whisper() -> WhisperWrapper:
    """取得 WhisperWrapper 單例"""
    global _whisper
    if _whisper is None:
        _whisper = WhisperWrapper()
    return _whisper
