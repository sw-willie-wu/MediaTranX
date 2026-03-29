"""
Basic Pitch 封裝 — 音訊轉 MIDI（非鼓類音軌）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
繼承 PackageRuntime，使用 Spotify basic-pitch（TFLite/ONNX, CPU-only）
將音訊轉換為 MIDI note 事件
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

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
        """載入 basic-pitch predict 函式"""
        from basic_pitch.inference import predict

        if on_progress:
            on_progress(0.3, "正在載入 Basic Pitch 模型...")

        logger.info("Basic Pitch predict function loaded")
        return predict

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
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> dict:
        """
        將音訊轉換為 MIDI note 事件

        Args:
            audio_path: 輸入音訊路徑
            on_progress: 進度回調

        Returns:
            track dict: {"name": ..., "instrument": 0, "is_drum": False, "notes": [...]}
            每個 note: {"pitch": int, "start": float, "duration": float, "velocity": int}
        """
        if on_progress:
            on_progress(0.0, "準備音訊轉 MIDI...")

        with self.acquire(
            model_id="basic_pitch",
            variant="default",
            on_progress=on_progress,
        ) as predict_fn:
            if on_progress:
                on_progress(0.3, "分析音訊中...")

            # predict() 回傳 (model_output, midi_data, note_events)
            model_output, midi_data, note_events = predict_fn(audio_path)

            if on_progress:
                on_progress(0.8, "轉換 MIDI 事件...")

        # 從音訊路徑取得 stem 名稱
        stem_name = Path(audio_path).stem

        # 轉換 note_events 為標準格式
        # note_events 是 Note namedtuple 列表：
        #   start_time_s, end_time_s, pitch_midi, amplitude, bends
        notes = []
        for event in note_events:
            velocity = int(min(127, max(1, event.amplitude * 127)))
            duration = event.end_time_s - event.start_time_s
            notes.append({
                "pitch": int(event.pitch_midi),
                "start": float(event.start_time_s),
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
