"""
GGUFRuntime - llama-cpp-python 格式執行器
負責大語言模型的載入與推理（如 TranslateGemma, Qwen3）
"""
import logging
from pathlib import Path
from typing import Optional, Callable, Any

from .runtime import BaseRuntime

logger = logging.getLogger(__name__)


class GGUFRuntime(BaseRuntime):
    """
    GGUF 執行器（基於 llama-cpp-python）
    
    特性：
    1. 單檔模型（.gguf）
    2. 支援 GPU 層數分配（n_gpu_layers）
    3. 預留 DirectML 支援介面
    """
    
    def _load_model_impl(
        self,
        model_path: Path,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> Any:
        """
        載入 GGUF 模型
        
        Args:
            model_path: .gguf 檔案路徑
            config: 配置字典（含 layers, n_ctx, device 等）
        
        Returns:
            llama_cpp.Llama 實例
        """
        if on_progress:
            on_progress(0.2, "正在初始化 llama.cpp...")
        
        from llama_cpp import Llama
        from backend.core.device import has_nvidia_gpu
        
        # 從配置提取參數
        n_ctx = config.get("n_ctx", 2048)
        layers = config.get("layers", 0)
        
        # GPU 層數分配策略
        n_gpu_layers = 0
        if has_nvidia_gpu():
            n_gpu_layers = layers  # 全層上 GPU
            logger.info(f"Allocating {n_gpu_layers} layers to GPU")
        else:
            logger.info("No NVIDIA GPU detected, using CPU only")
        
        # 預留 DirectML 分支（未來擴展）
        # if has_directml():
        #     n_gpu_layers = layers
        #     # 需要 llama-cpp-python DirectML 編譯版本
        
        if on_progress:
            on_progress(0.5, f"正在載入 GGUF 模型...")
        
        model = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        
        logger.info(
            f"GGUF model loaded: {model_path.name} "
            f"(n_ctx={n_ctx}, n_gpu_layers={n_gpu_layers})"
        )
        return model
    
    def _unload_model_impl(self) -> None:
        """
        卸載 GGUF 模型
        
        llama-cpp-python 的 Llama 物件可以安全釋放
        （不需要 _zombie_models 防護）
        """
        if self._model is not None:
            logger.info("Unloading GGUF model")
            # llama-cpp 會在 __del__ 自動釋放資源
            # 無需額外處理
    
    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        解析 GGUF 格式的模型路徑
        
        GGUF 格式特性：
        - 單檔 .gguf
        - 需指定 size 與 quantization
        - 從 registry 讀取 layers, n_ctx 等參數
        """
        from backend.core.ai.registry import FORMAT_GGUF, MODELS_REGISTRY
        
        family = MODELS_REGISTRY[FORMAT_GGUF].get(model_id)
        if not family:
            raise ValueError(f"Unknown GGUF model: {model_id}")
        
        # variant 格式："{size}:{quant}" 或 "{size}" (使用預設量化)
        if ":" in (variant or ""):
            size, quant = variant.split(":", 1)
        else:
            size = variant
            quant = family["default_variant"].get(size)
            if not quant:
                raise ValueError(f"No default quantization for {model_id}/{size}")
        
        # 獲取規格
        specs = family["specs"].get(size)
        if not specs:
            raise ValueError(f"Unknown size '{size}' for {model_id}")
        
        variant_spec = specs["variants"].get(quant)
        if not variant_spec:
            raise ValueError(f"Unknown quantization '{quant}' for {model_id}/{size}")
        
        # 透過 ModelManager 下載/驗證
        model_path = self._manager.get_model_path(model_id, f"{size}:{quant}")
        if not model_path:
            raise FileNotFoundError(
                f"Model not downloaded: {model_id}/{size}/{quant}. "
                f"Please download from HuggingFace: {variant_spec['repo_id']}"
            )
        
        config = {
            "model_id": model_id,
            "size": size,
            "quantization": quant,
            "layers": specs["layers"],
            "n_ctx": specs["n_ctx"],
            "vram_overhead_mb": specs["vram_overhead_mb"],
            "repo_id": variant_spec["repo_id"],
            "filename": variant_spec["filename"],
        }
        
        return model_path, config
