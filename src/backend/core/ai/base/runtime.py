"""
BaseRuntime - 所有模型執行器的抽象基類
負責統一的生命週期管理與 VRAM 鎖協調
"""
import logging
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class BaseRuntime(ABC):
    """
    模型執行器基類
    
    職責：
    1. 管理模型的載入/卸載生命週期
    2. 透過 ModelManager 獲取 VRAM 鎖
    3. 提供 @contextmanager 的 acquire() 介面
    """
    
    def __init__(self, slot: str):
        """
        Args:
            slot: 模型插槽名稱（用於 VRAM 鎖協調）
        """
        self._slot = slot
        self._lock = threading.RLock()
        self._model: Optional[Any] = None
        self._current_config: Optional[dict] = None
        
        # 延遲 import 避免循環依賴
        from backend.core.ai.model_manager import get_model_manager
        self._manager = get_model_manager()
        
        # 註冊卸載回調
        self._manager.register_unloader(slot, self._unload_model)
        
        logger.debug(f"BaseRuntime initialized for slot: {slot}")
    
    @abstractmethod
    def _load_model_impl(
        self, 
        model_path: Any,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> Any:
        """
        子類實作：載入模型的具體邏輯
        
        Args:
            model_path: 模型路徑（可能是 Path 或 str）
            config: 模型配置字典
            on_progress: 進度回調
            
        Returns:
            載入的模型物件
        """
        pass
    
    @abstractmethod
    def _unload_model_impl(self) -> None:
        """
        子類實作：卸載模型的具體邏輯
        注意：某些格式（如 BIN）需要特殊處理以避免 Windows 崩潰
        """
        pass
    
    def _unload_model(self) -> None:
        """統一的卸載入口（由 ModelManager 呼叫）"""
        with self._lock:
            if self._model is not None:
                logger.info(f"Unloading model from slot: {self._slot}")
                self._unload_model_impl()
                self._model = None
                self._current_config = None
                self._manager.release(self._slot)
    
    @contextmanager
    def acquire(
        self, 
        model_id: str, 
        variant: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None
    ):
        """
        獲取模型實例的 Context Manager
        
        使用範例：
            with runtime.acquire("whisper", "medium") as model:
                result = model.transcribe(audio)
        
        Args:
            model_id: 模型家族 ID
            variant: 模型變體（如 size, quantization）
            on_progress: 載入進度回調
            
        Yields:
            載入的模型物件
        """
        with self._lock:
            # 檢查是否需要重新載入
            config_key = f"{model_id}:{variant}"
            needs_reload = (
                self._model is None or 
                self._current_config is None or
                self._current_config.get("_key") != config_key
            )
            
            if needs_reload:
                # 卸載舊模型
                if self._model is not None:
                    self._unload_model_impl()
                    self._model = None
                
                # 獲取 VRAM 鎖
                self._manager.acquire(self._slot)
                
                # 載入新模型
                if on_progress:
                    on_progress(0.0, "正在準備模型...")
                
                model_path, config = self._resolve_model_path(model_id, variant)
                config["_key"] = config_key
                
                self._model = self._load_model_impl(model_path, config, on_progress)
                self._current_config = config
                
                if on_progress:
                    on_progress(1.0, "模型載入完成")
            
            yield self._model
    
    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        解析模型路徑與配置（由子類覆寫以支援不同格式）
        
        Returns:
            (model_path, config_dict)
        """
        # 預設實作：從 ModelManager 獲取
        path = self._manager.get_model_path(model_id, variant)
        config = {"model_id": model_id, "variant": variant}
        return path, config
    
    def is_loaded(self) -> bool:
        """檢查模型是否已載入"""
        return self._model is not None
    
    def get_current_config(self) -> Optional[dict]:
        """獲取當前載入的模型配置"""
        return self._current_config.copy() if self._current_config else None
