"""
BaseRuntime - abstract base class for all model executors.
Responsible for unified lifecycle management and VRAM lock coordination.
"""
import logging
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class BaseRuntime(ABC):
    """
    Model executor base class.

    Responsibilities:
    1. Manage model load/unload lifecycle
    2. Acquire VRAM locks via ModelManager
    3. Provide @contextmanager acquire() interface
    """

    def __init__(self, slot: str):
        """
        Args:
            slot: Model slot name (used for VRAM lock coordination).
        """
        self._slot = slot
        self._lock = threading.RLock()
        self._model: Optional[Any] = None
        self._current_config: Optional[dict] = None
        
        # Lazy import to avoid circular dependency
        from app.init.container import get_container
        self._manager = get_container().model_manager()
        
        # Register unload callback
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
        Subclass implementation: concrete model loading logic.

        Args:
            model_path: Model path (may be Path or str).
            config: Model configuration dict.
            on_progress: Progress callback.

        Returns:
            Loaded model object.
        """
        pass
    
    @abstractmethod
    def _unload_model_impl(self) -> None:
        """
        Subclass implementation: concrete model unloading logic.
        Note: some formats (e.g. BIN) require special handling to avoid Windows crashes.
        """
        pass
    
    def _unload_model(self) -> None:
        """Unified unload entry point (called by ModelManager)."""
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
        Context manager for acquiring a model instance.

        Example usage:
            with runtime.acquire("whisper", "medium") as model:
                result = model.transcribe(audio)

        Args:
            model_id: Model family ID.
            variant: Model variant (e.g. size, quantization).
            on_progress: Loading progress callback.

        Yields:
            Loaded model object.
        """
        with self._lock:
            # Check if reload is needed
            config_key = f"{model_id}:{variant}"
            needs_reload = (
                self._model is None or 
                self._current_config is None or
                self._current_config.get("_key") != config_key
            )
            
            if needs_reload:
                # Unload old model
                if self._model is not None:
                    self._unload_model_impl()
                    self._model = None
                
                # Acquire VRAM lock
                self._manager.acquire(self._slot)
                
                # Load new model
                if on_progress:
                    on_progress(0.0, "task.progress.preparing_model")
                
                model_path, config = self._resolve_model_path(model_id, variant)
                config["_key"] = config_key
                
                self._model = self._load_model_impl(model_path, config, on_progress)
                self._current_config = config
                
                if on_progress:
                    on_progress(1.0, "task.progress.model_loaded")
            
            yield self._model
    
    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        Resolve model path and configuration (override in subclasses for different formats).
        
        Returns:
            (model_path, config_dict)
        """
        # Default implementation: get from ModelManager
        path = self._manager.get_model_path(model_id, variant)
        config = {"model_id": model_id, "variant": variant}
        return path, config
    
    def is_loaded(self) -> bool:
        """Check if a model is loaded."""
        return self._model is not None
    
    def get_current_config(self) -> Optional[dict]:
        """Get the currently loaded model configuration."""
        return self._current_config.copy() if self._current_config else None
