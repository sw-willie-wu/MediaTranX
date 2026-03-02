"""
PTHRuntime - PyTorch 格式執行器
負責影像處理模型的載入（如 Real-ESRGAN, SwinIR）
"""
import logging
import torch
from pathlib import Path
from typing import Optional, Callable, Any

from .runtime import BaseRuntime

logger = logging.getLogger(__name__)


class PTHRuntime(BaseRuntime):
    """
    PTH 執行器（基於 PyTorch / Spandrel）
    
    特性：
    1. 單檔權重檔（.pth）
    2. 支援 CUDA/CPU 自動切換
    3. 預留 DirectML 支援介面
    4. 可選 Spandrel 通用載入器
    """
    
    def __init__(self, slot: str, use_spandrel: bool = True):
        """
        Args:
            slot: 模型插槽
            use_spandrel: 是否使用 Spandrel 通用架構載入器
        """
        super().__init__(slot)
        self._use_spandrel = use_spandrel
        self._device = None
    
    def _load_model_impl(
        self,
        model_path: Path,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> Any:
        """
        載入 PTH 模型
        
        Args:
            model_path: .pth 檔案路徑
            config: 配置字典（含 arch, device 等）
        
        Returns:
            PyTorch 模型實例
        """
        if on_progress:
            on_progress(0.2, "正在初始化 PyTorch...")
        
        # 設備選擇邏輯
        device = self._select_device(config.get("device"))
        self._device = device
        
        if on_progress:
            on_progress(0.4, f"正在載入權重檔 ({device})...")
        
        if self._use_spandrel:
            model = self._load_with_spandrel(model_path, device, config)
        else:
            model = self._load_with_torch(model_path, device, config)
        
        logger.info(f"PTH model loaded: {model_path.name} on {device}")
        return model
    
    def _load_with_spandrel(self, model_path: Path, device: str, config: dict) -> Any:
        """使用 Spandrel 通用載入器（自動識別架構）"""
        try:
            import spandrel
            model = spandrel.ModelLoader().load_from_file(str(model_path))
            model = model.to(device)
            model.eval()
            logger.info(f"Loaded via Spandrel: {type(model).__name__}")
            return model
        except ImportError:
            logger.warning("Spandrel not available, falling back to torch.load")
            return self._load_with_torch(model_path, device, config)
    
    def _load_with_torch(self, model_path: Path, device: str, config: dict) -> Any:
        """使用原生 PyTorch 載入（需子類提供架構）"""
        state_dict = torch.load(str(model_path), map_location=device)
        
        # 子類需覆寫 _build_arch() 提供模型架構
        if hasattr(self, '_build_arch'):
            model = self._build_arch(config)
            model.load_state_dict(state_dict, strict=True)
            model = model.to(device)
            model.eval()
            return model
        else:
            raise NotImplementedError(
                "Subclass must implement _build_arch() or enable use_spandrel=True"
            )
    
    def _select_device(self, preferred_device: Optional[str] = None) -> str:
        """
        選擇計算設備（預留 DirectML 擴展點）
        
        優先順序：
        1. preferred_device（如果有效）
        2. CUDA（如果可用）
        3. DirectML（未來擴展）
        4. CPU（回退）
        """
        if preferred_device:
            return preferred_device
        
        # CUDA 檢測
        if torch.cuda.is_available():
            return "cuda"
        
        # DirectML 檢測（預留）
        # if has_directml():
        #     return "dml"  # 需要 torch-directml 或 onnxruntime-directml
        
        logger.info("No GPU acceleration available, using CPU")
        return "cpu"
    
    def _unload_model_impl(self) -> None:
        """
        卸載 PTH 模型
        
        PyTorch 模型可以安全釋放，但需清空 CUDA cache
        """
        if self._model is not None:
            logger.info("Unloading PTH model")
            
            # 清空 CUDA cache
            if self._device and "cuda" in self._device:
                try:
                    torch.cuda.empty_cache()
                    logger.info("CUDA cache cleared")
                except Exception as e:
                    logger.warning(f"Failed to clear CUDA cache: {e}")
    
    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        解析 PTH 格式的模型路徑
        
        PTH 格式特性：
        - 單檔 .pth
        - 可能有多個變體（如 x2plus, x4plus）
        """
        from backend.core.ai.registry import FORMAT_PTH, MODELS_REGISTRY
        
        family = MODELS_REGISTRY[FORMAT_PTH].get(model_id)
        if not family:
            raise ValueError(f"Unknown PTH model: {model_id}")
        
        # 預設使用第一個變體
        if not variant:
            variant = list(family["variants"].keys())[0]
        
        variant_spec = family["variants"].get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown variant '{variant}' for {model_id}")
        
        # 透過 ModelManager 下載/驗證
        model_path = self._manager.get_model_path(model_id, variant)
        if not model_path:
            # PTH 格式可能是本地檔案（無 repo_id）
            from backend.core.paths import get_models_dir
            local_path = get_models_dir() / family["slot"] / variant_spec["filename"]
            if local_path.exists():
                model_path = local_path
            else:
                raise FileNotFoundError(
                    f"Model not found: {model_id}/{variant}. "
                    f"Expected at: {local_path}"
                )
        
        config = {
            "model_id": model_id,
            "variant": variant,
            "vram_mb": variant_spec.get("vram_mb", 2000),
            "arch": variant_spec.get("arch"),
            "scale": variant_spec.get("scale", 4),
        }
        
        return model_path, config
