"""
超解析基礎類別
子類只需實作 _load_model() 和 _run_enhance()，
VRAM 生命週期（acquire/release/lock）由基類統一管理。
"""
import logging
import threading
from abc import abstractmethod
from typing import Optional, Callable

from PIL import Image

from backend.core.ai.model_manager import get_model_manager, SLOT_UPSCALE

logger = logging.getLogger(__name__)


class BaseUpscaler:
    SLOT = SLOT_UPSCALE
    # 子類定義：{ model_id: vram_mb }
    VRAM_MB: dict = {}

    def __init__(self):
        self._model = None
        self._current_model_id: Optional[str] = None
        self._lock = threading.Lock()
        get_model_manager().register_unloader(self.SLOT, self._unload_model)

    def _unload_model(self) -> None:
        """釋放模型資源（由 ModelManager eviction 或主動呼叫）"""
        with self._lock:
            if self._model is not None:
                self._model = None
                self._current_model_id = None
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
                get_model_manager().release(self.SLOT)
                logger.info(f"{self.__class__.__name__} unloaded")

    @abstractmethod
    def _load_model(self, model_id: str, on_progress: Optional[Callable] = None) -> None:
        """載入指定模型，結果存入 self._model"""

    @abstractmethod
    def _run_enhance(self, image: Image.Image, scale: int) -> Image.Image:
        """執行推理，回傳增強後的圖片"""

    def enhance(
        self,
        image: Image.Image,
        model_id: str,
        scale: int = 4,
        on_progress: Optional[Callable] = None,
    ) -> Image.Image:
        """
        執行超解析推理。
        acquire() 在 lock 外呼叫，避免與 eviction callback 死鎖。
        """
        vram_mb = self.VRAM_MB.get(model_id, 2000)
        get_model_manager().acquire(self.SLOT, required_vram_mb=vram_mb)

        with self._lock:
            if self._current_model_id != model_id or self._model is None:
                self._load_model(model_id, on_progress)
            return self._run_enhance(image, scale)
