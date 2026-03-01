"""
模型與 VRAM 管理中心 (REFACTOR V4)
負責模型的註冊、下載、雜湊驗證與顯存調度。
遵循 DEVELOPMENT.md 單例規範。
"""
import os
import sys
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Callable, Set, Any
from contextlib import contextmanager

from backend.core.paths import get_models_dir, get_base_data_dir
from backend.core.device import has_nvidia_gpu

logger = logging.getLogger(__name__)

# --- 模型 Slot 常數 (相容性) ---
SLOT_WHISPER = "whisper"
SLOT_TRANSLATEGEMMA = "translategemma"
SLOT_QWEN3 = "qwen3"
SLOT_UPSCALE = "upscale"

# --- 模型註冊表 ---
MODELS_REGISTRY = {
    "upscale": {
        "realesrgan-x4plus": {
            "repo_id": "sberbank-ai/Real-ESRGAN", # 範例
            "filename": "RealESRGAN_x4plus.pth",
            "size_mb": 64,
            "description": "通用超解析 (x4)"
        },
        "hat-l-x4": {
            "repo_id": "Facea/HAT", # 範例
            "filename": "HAT_L_X4.pth",
            "size_mb": 200,
            "description": "頂級品質超解析 (x4)"
        }
    },
    "llm": {
        "qwen2.5-1.5b-instruct": {
            "repo_id": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
            "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
            "size_mb": 1100,
            "description": "輕量級高效能翻譯模型"
        }
    }
}

class ModelManager:
    """
    模型管理器單例
    """
    _instance: Optional["ModelManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._lock = threading.RLock()  # RLock 允許 unloader callback 在 acquire() 內重入
        self._gpu_lock = threading.Lock()  # 顯存互斥鎖
        self._loaded_slots: Set[str] = set()
        self._unloaders: Dict[str, Callable[[], None]] = {}
        
        # 版本守門員：記錄當前要求的環境版本
        self.required_env_version = "1.0.0"
        
        self._initialized = True
        logger.info("ModelManager (V4) initialized")

    @contextmanager
    def gpu_session(self):
        """顯存鎖：確保影像處理與語言推理不會同時搶奪顯存"""
        logger.debug("Requesting GPU session...")
        with self._gpu_lock:
            yield
        logger.debug("GPU session ended.")

    def register_unloader(self, slot: str, callback: Callable[[], None]):
        """註冊模型卸載函數"""
        self._unloaders[slot] = callback

    def acquire(self, slot: str, required_vram_mb: int = 0) -> None:
        """
        申請加載 slot。
        - 若 slot 已加載則短路返回。
        - 否則驅逐其他已加載 slot 以釋放 VRAM，再標記此 slot 為已加載。
        注意：不呼叫 gc.collect()，避免 CTranslate2 destructor crash。
        """
        with self._lock:
            if slot in self._loaded_slots:
                return

            # 驅逐其他 slot
            for other_slot in list(self._loaded_slots):
                unloader = self._unloaders.get(other_slot)
                if unloader:
                    try:
                        unloader()
                        logger.info(f"Evicted slot: {other_slot}")
                    except Exception as e:
                        logger.error(f"Failed to evict {other_slot}: {e}")
            self._loaded_slots.clear()

            # 釋放 CUDA 快取（不呼叫 gc.collect，避免 CTranslate2 destructor crash）
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            self._loaded_slots.add(slot)
            logger.info(f"Acquired slot: {slot} (required_vram_mb={required_vram_mb})")

    def release(self, slot: str) -> None:
        """標記 slot 為已卸載（由模型自行呼叫 _unload_model 後通知）"""
        with self._lock:
            self._loaded_slots.discard(slot)

    def is_llama_ready(self) -> bool:
        """
        檢查 llama-cpp-python 是否已安裝且版本 >= 0.3.9（支援 Qwen3 的最低版本）。
        0.3.4（abetlen Windows wheel）不支援 Qwen3 架構，視為未就緒。
        """
        venv_path = get_base_data_dir() / ".venv"
        if not venv_path.exists():
            return False
        if not list(venv_path.glob("**/site-packages/llama_cpp")):
            return False
        # 版本檢查：0.3.4 不支援 Qwen3
        MIN_VERSION = (0, 3, 9)
        for dist_info in venv_path.glob("**/site-packages/llama_cpp_python-*.dist-info"):
            try:
                ver_str = dist_info.name.split("llama_cpp_python-")[1].split(".dist-info")[0]
                parts = ver_str.split("+")[0].split(".")
                ver = tuple(int(x) for x in parts[:3])
                if ver >= MIN_VERSION:
                    return True
                logger.info(f"llama-cpp-python {ver_str} < {MIN_VERSION} — needs upgrade (no Qwen3 support)")
                return False
            except Exception:
                pass
        return True  # 無法解析版本時假設 OK

    def is_ai_env_ready(self) -> bool:
        """
        檢查 .venv 是否已安裝 [ai] 插件，且 torch 版本符合硬體需求：
        - 無 NVIDIA GPU：torch 存在即可（CPU 版）
        - 有 NVIDIA GPU：需確認 CUDA DLL（cublas64_12.dll）存在於 torch/lib/
        """
        venv_path = get_base_data_dir() / ".venv"
        if not venv_path.exists():
            return False

        torch_dirs = list(venv_path.glob("**/site-packages/torch"))
        if not torch_dirs:
            return False

        # 有 NVIDIA GPU 時，確認 CUDA 版 torch（含 cublas DLL）
        if has_nvidia_gpu():
            torch_lib = torch_dirs[0] / "lib"
            cuda_dll = torch_lib / "cublas64_12.dll"
            return cuda_dll.exists()

        return True

    def get_model_path(self, category: str, model_id: str) -> Optional[Path]:
        """檢查模型是否存在並回傳路徑"""
        config = MODELS_REGISTRY.get(category, {}).get(model_id)
        if not config:
            return None
        
        # 這裡未來整合 huggingface_hub 的快取檢查
        target_path = get_models_dir(category) / config["filename"]
        return target_path if target_path.exists() else None

    async def download_model(self, category: str, model_id: str, on_progress: Callable[[float, str], None]):
        """下載模型 (支援斷點續傳)"""
        config = MODELS_REGISTRY.get(category, {}).get(model_id)
        if not config:
            raise ValueError(f"Unknown model: {model_id}")

        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            raise RuntimeError("AI 環境未就緒，無法下載模型")

        target_dir = get_models_dir(category)
        
        logger.info(f"Downloading {model_id} to {target_dir}...")
        on_progress(0.1, f"開始下載 {model_id}...")

        # 使用 huggingface_hub 的標準下載 (內建續傳)
        path = hf_hub_download(
            repo_id=config["repo_id"],
            filename=config["filename"],
            cache_dir=str(target_dir),
            resume_download=True
        )
        
        on_progress(1.0, "下載完成")
        return Path(path)

    def unload_all(self):
        """強制清空所有已註冊的模型顯存"""
        with self._lock:
            for slot, unloader in self._unloaders.items():
                try:
                    unloader()
                    logger.info(f"Evicted {slot}")
                except Exception as e:
                    logger.error(f"Failed to unload {slot}: {e}")
            
            self._loaded_slots.clear()
            
            # 強制清理 Torch 快取
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            

def get_model_manager() -> ModelManager:
    """取得單例實例"""
    return ModelManager()
