"""
PackageRuntime - 套件自管模型執行器
負責由第三方套件自行管理載入的模型（如 Whisper、Demucs）
"""
import logging
from abc import abstractmethod
from typing import Optional, Callable, Any

import torch

from .base import BaseRuntime

logger = logging.getLogger(__name__)


class PackageRuntime(BaseRuntime):
    """
    套件自管執行器

    適用於模型載入邏輯由第三方套件負責的情況（如 faster-whisper、demucs）。
    子類只需實作 _create_model() 和 _cleanup_model()。

    特性：
    1. 設備自動選擇（CUDA/CPU）
    2. 統一的卸載 + CUDA cache 清理
    3. 可覆寫 _cleanup_model() 做自訂清理（如 Windows 崩潰防護）
    """

    def __init__(self, slot: str):
        super().__init__(slot)
        self._device: Optional[str] = None

    @abstractmethod
    def _create_model(
        self,
        model_path: Any,
        config: dict,
        device: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """
        子類實作：建立模型物件

        Args:
            model_path: 模型路徑（目錄或檔案）
            config: 模型配置字典
            device: 計算設備（"cuda" / "cpu"）
            on_progress: 進度回調

        Returns:
            模型物件
        """
        pass

    def _load_model_impl(
        self,
        model_path: Any,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """載入模型（統一的設備選擇 + 委派給 _create_model）"""
        device = self._select_device(config.get("device"))
        self._device = device

        if on_progress:
            on_progress(0.1, "正在準備模型...")

        model = self._create_model(model_path, config, device, on_progress)

        logger.info(f"PackageRuntime model loaded on {device}")
        return model

    def _unload_model_impl(self) -> None:
        """卸載模型：先呼叫子類的清理邏輯，再清 CUDA cache"""
        if self._model is not None:
            logger.info(f"Unloading package model from slot: {self._slot}")
            self._cleanup_model()

            if self._device and "cuda" in self._device:
                try:
                    torch.cuda.empty_cache()
                    logger.info("CUDA cache cleared")
                except Exception as e:
                    logger.warning(f"Failed to clear CUDA cache: {e}")

    def _cleanup_model(self) -> None:
        """
        子類可覆寫：自訂清理邏輯

        例如 Whisper 需要 zombie 防護，Demucs 不需要。
        預設不做任何事。
        """
        pass

    def _select_device(self, preferred: Optional[str] = None) -> str:
        """
        選擇計算設備

        優先順序：
        1. preferred（如果指定）
        2. CUDA（如果可用）
        3. CPU（回退）
        """
        if preferred:
            return preferred

        try:
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass

        logger.info("No GPU acceleration available, using CPU")
        return "cpu"
