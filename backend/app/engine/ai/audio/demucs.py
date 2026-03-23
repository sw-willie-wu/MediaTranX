"""
Demucs 音源分離模組
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
繼承 PackageRuntime，使用 demucs 套件進行 6 軌音源分離
（vocals, drums, bass, guitar, piano, other）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

from app.engine.ai.runtime.package import PackageRuntime
from app.engine.ai.registry import FORMAT_PKG, MODELS_REGISTRY, SLOT_DEMUCS

logger = logging.getLogger(__name__)


class DemucsWrapper(PackageRuntime):
    """
    Demucs 音源分離封裝（繼承 PackageRuntime）

    職責：
    1. 6 軌音源分離（vocals, drums, bass, guitar, piano, other）
    2. 模型由 demucs 套件自行管理載入
    3. 設備自動切換由 PackageRuntime 處理
    """

    def __init__(self):
        super().__init__(slot=SLOT_DEMUCS)
        logger.info("DemucsWrapper initialized (PackageRuntime)")

    def _create_model(
        self,
        model_path: Any,
        config: dict,
        device: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """使用 demucs.api.Separator 載入模型"""
        import functools
        import torch
        from demucs.api import Separator
        from app.engine.paths import get_models_dir

        if on_progress:
            on_progress(0.3, "正在載入 Demucs 模型...")

        model_name = config.get("model_name", "htdemucs_6s")

        # 將 torch hub cache 指向 models/demucs/，讓 checkpoint 統一存放
        hub_dir = str(get_models_dir() / SLOT_DEMUCS)
        original_hub_dir = torch.hub.get_dir()
        torch.hub.set_dir(hub_dir)

        # PyTorch 2.6+ 預設 weights_only=True，demucs checkpoint 需要 weights_only=False
        _original_load = torch.load
        torch.load = functools.partial(_original_load, weights_only=False)
        try:
            separator = Separator(
                model=model_name,
                device=device,
                shifts=1,
                overlap=0.25,
            )
        finally:
            torch.load = _original_load
            torch.hub.set_dir(original_hub_dir)

        logger.info(f"Demucs Separator loaded: {model_name} on {device}")
        return separator

    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        解析 Demucs 模型路徑

        Demucs 模型由套件自行下載到 repo 目錄，
        這裡回傳 models/demucs/ 作為 repo 目錄。
        """
        family = MODELS_REGISTRY[FORMAT_PKG].get(model_id)
        if not family:
            raise ValueError(f"Unknown PKG model: {model_id}")

        variant_spec = family["variants"].get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown variant '{variant}' for {model_id}")

        config = {
            "model_id": model_id,
            "variant": variant,
            "model_name": variant_spec.get("model_name", variant),
            "vram_mb": variant_spec.get("vram_mb", 2000),
            "sources": variant_spec.get("sources", []),
        }

        # demucs 自行管理模型路徑（torch hub cache），回傳 None
        return None, config

    def get_model_status(self, variant: str = "htdemucs_6s") -> dict:
        """檢查模型是否可用（demucs 套件 + torch hub cache 中有 checkpoint）"""
        family = MODELS_REGISTRY[FORMAT_PKG].get("demucs")
        if not family:
            return {"available": False, "model_downloaded": False}

        variant_spec = family["variants"].get(variant)
        if not variant_spec:
            return {"available": False, "model_downloaded": False}

        # 檢查 demucs 套件是否已安裝
        try:
            from demucs.api import Separator  # noqa: F401
            available = True
        except (ImportError, ModuleNotFoundError):
            available = False

        # 檢查 models/demucs/checkpoints/ 是否有模型 checkpoint
        model_downloaded = False
        try:
            from app.engine.paths import get_models_dir
            checkpoints_dir = get_models_dir() / SLOT_DEMUCS / "checkpoints"
            if checkpoints_dir.exists():
                model_downloaded = any(f.suffix == ".th" for f in checkpoints_dir.iterdir())
        except Exception:
            pass

        return {
            "available": available,
            "model_downloaded": model_downloaded,
        }

    def separate(
        self,
        audio_path: str,
        variant: str = "htdemucs_6s",
        stems: Optional[List[str]] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> tuple[Dict[str, Any], int]:
        """
        執行音源分離

        Args:
            audio_path: 輸入音訊路徑
            variant: 模型變體
            stems: 要分離的音軌名稱（None=全部）
            on_progress: 進度回調

        Returns:
            ({stem_name: tensor}, sample_rate)
        """
        family = MODELS_REGISTRY[FORMAT_PKG]["demucs"]
        variant_spec = family["variants"][variant]
        all_sources = variant_spec["sources"]

        if on_progress:
            on_progress(0.0, "準備音源分離...")

        with self.acquire(
            model_id="demucs",
            variant=variant,
            on_progress=on_progress,
        ) as separator:
            if on_progress:
                on_progress(0.3, "分離音源中...")

            # Separator.separate_audio_file 處理：讀取、resample、分段、推論
            origin, separated = separator.separate_audio_file(audio_path)

            sample_rate = separator.samplerate

            if on_progress:
                on_progress(0.9, "處理結果...")

        # 篩選指定的 stems
        result = {}
        for source_name in all_sources:
            if stems and source_name not in stems:
                continue
            if source_name in separated:
                result[source_name] = separated[source_name].cpu()

        if on_progress:
            on_progress(1.0, "音源分離完成")

        return result, sample_rate


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_demucs: Optional[DemucsWrapper] = None


def get_demucs() -> DemucsWrapper:
    """取得 DemucsWrapper 單例"""
    global _demucs
    if _demucs is None:
        _demucs = DemucsWrapper()
    return _demucs
