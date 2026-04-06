"""
Basic Pitch 封裝 — 音訊轉 MIDI（非鼓類音軌）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
繼承 PackageRuntime，使用 Spotify basic-pitch（TFLite/ONNX, CPU-only）
將音訊轉換為 MIDI note 事件
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from basic_pitch import ICASSP_2022_MODEL_PATH

from app.engine.ai.runtime.package import PackageRuntime
from app.engine.ai.registry import FORMAT_PKG, MODELS_REGISTRY, SLOT_BASIC_PITCH

logger = logging.getLogger(__name__)


class BasicPitchWrapper(PackageRuntime):
    """
    Basic Pitch 音訊轉 MIDI 封裝（繼承 PackageRuntime）

    職責：
    1. 將非鼓類音軌轉換為 MIDI note 事件
    2. 模型由 basic-pitch 套件自行管理
    3. CPU-only，不需要 GPU
    """

    def __init__(self):
        super().__init__(slot=SLOT_BASIC_PITCH)
        logger.info("BasicPitchWrapper initialized (PackageRuntime)")

    def _create_model(
        self,
        model_path: Any,
        config: dict,
        device: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """載入 basic-pitch predict 函式和內建 ONNX 模型路徑"""
        from basic_pitch.inference import predict

        if on_progress:
            on_progress(0.3, "正在載入 Basic Pitch 模型...")

        logger.info(f"Basic Pitch loaded: model={ICASSP_2022_MODEL_PATH}")
        return {"predict": predict, "model_path": ICASSP_2022_MODEL_PATH}

    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        解析 Basic Pitch 模型路徑

        basic-pitch 自行管理模型（內建 TFLite/ONNX），回傳 None。
        """
        family = MODELS_REGISTRY[FORMAT_PKG].get(model_id)
        if not family:
            raise ValueError(f"Unknown PKG model: {model_id}")

        variant = variant or "default"
        variant_spec = family["variants"].get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown variant '{variant}' for {model_id}")

        config = {
            "model_id": model_id,
            "variant": variant,
            "model_name": variant_spec.get("model_name", variant),
            "vram_mb": variant_spec.get("vram_mb", 0),
        }

        # basic-pitch 自行管理模型路徑，回傳 None
        return None, config

    def get_model_status(self) -> dict:
        """檢查 basic-pitch 套件是否可用"""
        try:
            from basic_pitch.inference import predict  # noqa: F401
            available = True
        except (ImportError, ModuleNotFoundError):
            available = False

        return {
            "available": available,
            "model_downloaded": available,  # 模型內建於套件中
        }

    def audio_to_midi(
        self,
        audio_path: str,
        onset_threshold: float = 0.3,
        frame_threshold: float = 0.15,
        minimum_note_length: float = 80.0,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> dict:
        """
        將音訊轉換為 MIDI note 事件

        Args:
            audio_path: 輸入音訊路徑
            onset_threshold: onset 偵測門檻 (預設 0.3, basic-pitch 預設 0.5)
            frame_threshold: frame 偵測門檻 (預設 0.15, basic-pitch 預設 0.3)
            minimum_note_length: 最短音符長度 ms (預設 80, basic-pitch 預設 127.7)
            on_progress: 進度回調

        Returns:
            track dict: {"name": ..., "instrument": 0, "is_drum": False, "notes": [...]}
            每個 note: {"pitch": int, "start": float, "duration": float, "velocity": int}
        """
        if on_progress:
            on_progress(0.0, "準備音訊轉 MIDI...")

        # basic-pitch 內部使用 print/logging 輸出路徑，
        # 非 ASCII 檔名在 Windows cp950 環境會 crash。
        # 複製到 ASCII 安全的暫存路徑再處理。
        src = Path(audio_path)
        safe_path: str = str(src)
        tmp_dir = None
        try:
            src.name.encode("ascii")
        except UnicodeEncodeError:
            tmp_dir = tempfile.mkdtemp(prefix="bp_")
            safe_name = f"input{src.suffix}"
            safe_file = Path(tmp_dir) / safe_name
            shutil.copy2(src, safe_file)
            safe_path = str(safe_file)
            logger.debug("Copied non-ASCII path to temp: %s", safe_path)

        try:
            with self.acquire(
                model_id="basic_pitch",
                variant="default",
                on_progress=on_progress,
            ) as bp:
                if on_progress:
                    on_progress(0.3, "分析音訊中...")

                # predict(audio_path, model_or_model_path) 回傳 (model_output, midi_data, note_events)
                model_output, midi_data, note_events = bp["predict"](
                    safe_path,
                    bp["model_path"],
                    onset_threshold=onset_threshold,
                    frame_threshold=frame_threshold,
                    minimum_note_length=minimum_note_length,
                )

                if on_progress:
                    on_progress(0.8, "轉換 MIDI 事件...")
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # 從音訊路徑取得 stem 名稱
        stem_name = Path(audio_path).stem

        # 轉換 note_events 為標準格式
        # note_events 是 tuple 列表：(start_time_s, end_time_s, pitch_midi, amplitude, bends)
        notes = []
        for event in note_events:
            start_s, end_s, pitch, amplitude = event[0], event[1], event[2], event[3]
            velocity = int(min(127, max(1, amplitude * 127)))
            duration = end_s - start_s
            notes.append({
                "pitch": int(pitch),
                "start": float(start_s),
                "duration": float(duration),
                "velocity": velocity,
            })

        if on_progress:
            on_progress(1.0, "音訊轉 MIDI 完成")

        logger.info(f"Basic Pitch: {len(notes)} notes extracted from {stem_name}")

        return {
            "name": stem_name,
            "instrument": 0,
            "is_drum": False,
            "notes": notes,
        }


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_basic_pitch: Optional[BasicPitchWrapper] = None


def get_basic_pitch() -> BasicPitchWrapper:
    """取得 BasicPitchWrapper 單例"""
    global _basic_pitch
    if _basic_pitch is None:
        _basic_pitch = BasicPitchWrapper()
    return _basic_pitch
