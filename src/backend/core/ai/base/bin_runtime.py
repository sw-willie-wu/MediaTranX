"""
BINRuntime - CTranslate2 格式執行器
負責目錄型快照模型的載入（如 Whisper）
"""
import logging
from pathlib import Path
from typing import Optional, Callable, Any

from .runtime import BaseRuntime

logger = logging.getLogger(__name__)

# ⚠️ 關鍵防護機制：Windows 穩定性保障
# CTranslate2 的 C++ 解構子在 Windows 上會觸發 STATUS_STACK_BUFFER_OVERRUN 崩潰
# 必須保持已卸載模型的 Python 引用，防止解構子執行
_zombie_models: list = []


class BINRuntime(BaseRuntime):
    """
    CTranslate2 執行器
    
    特性：
    1. 目錄型模型（需下載整個 snapshot）
    2. 支援 unload_model() 釋放 CUDA 記憶體
    3. ⚠️ 必須保留 Python 物件引用（_zombie_models）
    """
    
    def _load_model_impl(
        self,
        model_path: Path,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> Any:
        """
        載入 CTranslate2 模型
        
        Args:
            model_path: 模型目錄路徑
            config: 配置字典（含 device, compute_type 等）
        
        Returns:
            CTranslate2 模型實例
        """
        if on_progress:
            on_progress(0.2, "正在初始化 CTranslate2...")
        
        from faster_whisper import WhisperModel
        from backend.core.device import get_device, get_compute_type
        
        device = config.get("device", get_device())
        compute_type = config.get("compute_type", get_compute_type())
        
        if on_progress:
            on_progress(0.5, f"正在載入模型 ({device})...")
        
        model = WhisperModel(
            str(model_path),
            device=device,
            compute_type=compute_type,
        )
        
        logger.info(f"CTranslate2 model loaded: {model_path} on {device}")
        return model
    
    def _unload_model_impl(self) -> None:
        """
        卸載 CTranslate2 模型
        
        ⚠️ 關鍵步驟：
        1. 呼叫 unload_model() 釋放 CUDA 記憶體
        2. 將物件加入 _zombie_models 防止 C++ 解構
        """
        if self._model is None:
            return
        
        # Step 1: 釋放 CUDA 記憶體
        try:
            if hasattr(self._model, 'model') and hasattr(self._model.model, 'unload_model'):
                self._model.model.unload_model()
                logger.info("CTranslate2 CUDA memory released via unload_model()")
        except Exception as e:
            logger.warning(f"CTranslate2 unload_model() failed: {e}")
        
        # Step 2: ⚠️ 殭屍化物件（Windows 崩潰防護）
        _zombie_models.append(self._model)
        logger.debug(f"Model zombified (total zombies: {len(_zombie_models)})")
    
    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        解析 BIN 格式的模型路徑
        
        BIN 格式特性：
        - 是目錄（非單檔）
        - 從 HuggingFace 下載完整 snapshot
        """
        from backend.core.ai.registry import FORMAT_BIN, MODELS_REGISTRY
        
        family = MODELS_REGISTRY[FORMAT_BIN].get(model_id)
        if not family:
            raise ValueError(f"Unknown BIN model: {model_id}")
        
        size_config = family["variants"].get(variant)
        if not size_config:
            raise ValueError(f"Unknown variant '{variant}' for {model_id}")
        
        # 透過 ModelManager 下載/驗證
        model_path = self._manager.get_model_path(model_id, variant)
        if not model_path:
            raise FileNotFoundError(
                f"Model not downloaded: {model_id}/{variant}. "
                f"Please download from HuggingFace: {size_config['repo_id']}"
            )
        
        config = {
            "model_id": model_id,
            "variant": variant,
            "repo_id": size_config["repo_id"],
            "vram_mb": size_config["vram_mb"],
        }
        
        return model_path, config
