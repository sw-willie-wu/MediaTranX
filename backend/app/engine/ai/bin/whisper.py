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

from app.engine.ai.base import BINRuntime
from app.engine.ai.registry import SLOT_WHISPER, FORMAT_BIN, MODELS_REGISTRY

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


# ═══════════════════════════════════════════════════════════
# 詞級時間戳 → 智慧分句
# ═══════════════════════════════════════════════════════════
# 停頓間隔閾值（秒）：連續兩個 word 間隔超過此值視為可拆點
_PAUSE_THRESHOLD_S = 0.3
# 單行字數上限：超過此字數且有停頓點時，優先拆行
_MAX_CHARS_PER_LINE = 42


def _split_by_words(words: list) -> list[TranscribeSegment]:
    """
    用 word-level 時間戳做智慧分句。

    策略：
    1. 修正時間戳 — start/end 取自首尾 word（去掉 VAD padding）
    2. 長句拆行 — 在最大停頓處切開，確保每行不會太長
    3. 保持句意完整 — 不逐詞拆，翻譯仍拿到完整片語
    """
    if not words:
        return []

    # 找所有候選切點：word 間的停頓間隔
    pause_points: list[tuple[int, float]] = []  # (index, gap_seconds)
    for i in range(1, len(words)):
        gap = words[i].start - words[i - 1].end
        if gap >= _PAUSE_THRESHOLD_S:
            pause_points.append((i, gap))

    # 如果整句夠短或沒有停頓點，直接修正時間戳輸出一句
    total_text = "".join(w.word for w in words).strip()
    if not pause_points or len(total_text) <= _MAX_CHARS_PER_LINE:
        return [TranscribeSegment(
            start=words[0].start,
            end=words[-1].end,
            text=total_text,
        )]

    # 遞迴式拆行：每次在最大停頓處切一刀
    result: list[TranscribeSegment] = []
    _recursive_split(words, pause_points, result)
    return result


def _recursive_split(
    words: list,
    pause_points: list[tuple[int, float]],
    result: list[TranscribeSegment],
) -> None:
    """在最大停頓處切開，子片段超長則繼續遞迴拆。"""
    text = "".join(w.word for w in words).strip()

    # 篩選出屬於當前 words 範圍的 pause_points
    if not pause_points or len(text) <= _MAX_CHARS_PER_LINE:
        result.append(TranscribeSegment(
            start=words[0].start,
            end=words[-1].end,
            text=text,
        ))
        return

    # 找最大停頓
    best = max(pause_points, key=lambda p: p[1])
    split_idx = best[0]

    left_words = words[:split_idx]
    right_words = words[split_idx:]
    left_pauses = [(i, g) for i, g in pause_points if i < split_idx]
    right_pauses = [(i - split_idx, g) for i, g in pause_points if i > split_idx]

    _recursive_split(left_words, left_pauses, result)
    _recursive_split(right_words, right_pauses, result)


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
        
        from app.engine.paths import get_base_data_dir
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
                    if word_timestamps and segment.words:
                        # 詞級時間戳：用 word 時間修正句子邊界 + 長句智慧拆行
                        sub_segs = _split_by_words(segment.words)
                        segments.extend(sub_segs)
                    else:
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
