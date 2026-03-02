"""
模型與 VRAM 管理中心 (Three-Layer Architecture V6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
負責：
1. 模型註冊與下載協調
2. VRAM 調度與插槽管理  
3. 提供導航器 API 供 Runtime 使用
"""
import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Callable, Set

from backend.core.paths import get_models_dir, get_base_data_dir
from .registry import (
    MODELS_REGISTRY,
    FORMAT_BIN,
    FORMAT_GGUF,
    FORMAT_PTH,
)

logger = logging.getLogger(__name__)

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
        
        self._lock = threading.RLock()
        self._gpu_lock = threading.Lock()
        self._loaded_slots: Set[str] = set()
        self._unloaders: Dict[str, Callable[[], None]] = {}
        
        self._initialized = True
        logger.info("ModelManager (V5) initialized with Registry")

    @contextmanager
    def gpu_session(self):
        """顯存鎖：確保影像處理與語言推理不會同時搶奪顯存"""
        with self._gpu_lock:
            yield

    def register_unloader(self, slot: str, callback: Callable[[], None]):
        """註冊模型卸載函數"""
        self._unloaders[slot] = callback

    def acquire(self, slot: str, required_vram_mb: int = 0) -> None:
        """申請加載 slot。驅逐其他已加載 slot 以釋放 VRAM。"""
        with self._lock:
            if slot in self._loaded_slots:
                return

            for other_slot in list(self._loaded_slots):
                unloader = self._unloaders.get(other_slot)
                if unloader:
                    try:
                        unloader()
                        logger.info(f"Evicted slot: {other_slot}")
                    except Exception as e:
                        logger.error(f"Failed to evict {other_slot}: {e}")
            self._loaded_slots.clear()

            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            self._loaded_slots.add(slot)
            logger.info(f"Acquired slot: {slot} (required VRAM: {required_vram_mb}MB)")

    def release(self, slot: str) -> None:
        """標記 slot 為已卸載"""
        with self._lock:
            self._loaded_slots.discard(slot)

    # ═══════════════════════════════════════════════════════
    # 導航器 API（Navigator APIs）
    # ═══════════════════════════════════════════════════════
    
    def get_model_format(self, model_id: str) -> Optional[str]:
        """
        查詢模型所屬格式
        
        Returns:
            FORMAT_BIN / FORMAT_GGUF / FORMAT_PTH / None
        """
        for fmt in [FORMAT_BIN, FORMAT_GGUF, FORMAT_PTH]:
            if model_id in MODELS_REGISTRY[fmt]:
                return fmt
        return None
    
    def get_model_config(self, model_id: str, variant: Optional[str] = None) -> Optional[Dict]:
        """
        獲取模型完整配置
        
        Returns:
            配置字典（含 repo_id, vram_mb, layers 等）
        """
        fmt = self.get_model_format(model_id)
        if not fmt:
            return None
        
        family = MODELS_REGISTRY[fmt][model_id]
        
        if fmt == FORMAT_BIN:
            # Whisper: sizes -> variant
            return family["sizes"].get(variant) if variant else None
        
        elif fmt == FORMAT_GGUF:
            # LLM: specs -> size -> variants -> quant
            if not variant:
                return None
            if ":" in variant:
                size, quant = variant.split(":", 1)
            else:
                size = variant
                quant = family["default_variant"].get(size)
            
            spec = family["specs"].get(size)
            if not spec:
                return None
            
            variant_spec = spec["variants"].get(quant)
            if not variant_spec:
                return None
            
            # 合併 spec 與 variant_spec
            return {
                **variant_spec,
                "layers": spec["layers"],
                "n_ctx": spec["n_ctx"],
                "vram_overhead_mb": spec["vram_overhead_mb"],
            }
        
        elif fmt == FORMAT_PTH:
            # PTH: variants -> variant
            return family["variants"].get(variant) if variant else None
        
        return None
    
    def get_vram_requirement(self, model_id: str, variant: Optional[str] = None) -> int:
        """
        獲取模型 VRAM 需求（MB）
        
        Returns:
            VRAM 需求（MB），失敗返回 0
        """
        config = self.get_model_config(model_id, variant)
        if not config:
            return 0
        
        # BIN/PTH 格式直接有 vram_mb
        if "vram_mb" in config:
            return config["vram_mb"]
        
        # GGUF 格式：size_mb + vram_overhead_mb
        if "size_mb" in config and "vram_overhead_mb" in config:
            return config["size_mb"] + config["vram_overhead_mb"]
        
        return 0
    
    def get_model_path(self, model_id: str, variant: Optional[str] = None) -> Optional[Path]:
        """
        取得模型本地路徑（適配新的格式優先註冊表）
        
        Args:
            model_id: 模型家族 ID（如 "whisper", "translategemma", "realesrgan"）
            variant: 變體（如 "medium", "4b:Q4_K_M", "x4plus"）
        
        Returns:
            模型路徑（目錄或檔案），不存在返回 None
        """
        fmt = self.get_model_format(model_id)
        if not fmt:
            logger.warning(f"Unknown model_id: {model_id}")
            return None
        
        family = MODELS_REGISTRY[fmt][model_id]
        slot = family.get("slot", "")
        base_dir = get_models_dir() / slot
        
        # BIN 格式（目錄型）
        if fmt == FORMAT_BIN:
            target = base_dir / variant if variant else base_dir
            # 檢查關鍵檔案判斷完整性
            marker = target / "model.bin"
            return target if marker.exists() else None
        
        # GGUF 格式（單檔型）
        elif fmt == FORMAT_GGUF:
            config = self.get_model_config(model_id, variant)
            if not config or "filename" not in config:
                return None
            target = base_dir / config["filename"]
            return target if target.exists() else None
        
        # PTH 格式（單檔型）
        elif fmt == FORMAT_PTH:
            if not variant:
                # 默認使用第一個變體
                variant = list(family["variants"].keys())[0]
            variant_spec = family["variants"].get(variant)
            if not variant_spec or "filename" not in variant_spec:
                return None
            target = base_dir / variant_spec["filename"]
            return target if target.exists() else None
        
        return None


    async def download_model(
        self,
        model_id: str,
        variant: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> Path:
        """
        統一的下載邏輯（適配新的格式優先註冊表）
        
        Args:
            model_id: 模型家族 ID
            variant: 變體
            on_progress: 進度回調
            
        Returns:
            下載後的路徑
        """
        
        fmt = self.get_model_format(model_id)
        if not fmt:
            raise ValueError(f"Unknown model: {model_id}")
        
        family = MODELS_REGISTRY[fmt][model_id]
        slot = family.get("slot", "")
        base_dir = get_models_dir() / slot
        base_dir.mkdir(parents=True, exist_ok=True)
        
        if on_progress:
            on_progress(0.1, f"開始下載 {model_id}...")
        
        # BIN 格式（目錄型快照）
        if fmt == FORMAT_BIN:
            config = self.get_model_config(model_id, variant)
            if not config or "repo_id" not in config:
                raise ValueError(f"Invalid BIN config for {model_id}/{variant}")
            
            local_dir = base_dir / variant
            path = await self._async_snapshot_download(
                repo_id=config["repo_id"],
                local_dir=str(local_dir),
                on_progress=on_progress
            )
            return Path(path)
        
        # GGUF 或 PTH 格式（單檔）
        else:
            config = self.get_model_config(model_id, variant)
            if not config or "repo_id" not in config or "filename" not in config:
                raise ValueError(f"Invalid config for {model_id}/{variant}")
            
            path = await self._async_hf_hub_download(
                repo_id=config["repo_id"],
                filename=config["filename"],
                local_dir=str(base_dir),
                on_progress=on_progress
            )
            return Path(path)
    
    async def _async_snapshot_download(
        self,
        repo_id: str,
        local_dir: str,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """異步下載 HuggingFace snapshot"""
        import asyncio
        from huggingface_hub import snapshot_download as _snapshot_download
        
        def _download():
            return _snapshot_download(repo_id=repo_id, local_dir=local_dir)
        
        path = await asyncio.to_thread(_download)
        
        if on_progress:
            on_progress(1.0, "下載完成")
        
        return path
    
    async def _async_hf_hub_download(
        self,
        repo_id: str,
        filename: str,
        local_dir: str,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """異步下載 HuggingFace 單檔"""
        import asyncio
        from huggingface_hub import hf_hub_download as _hf_hub_download
        
        def _download():
            return _hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=local_dir
            )
        
        path = await asyncio.to_thread(_download)
        
        if on_progress:
            on_progress(1.0, "下載完成")
        
        return path

    def is_ai_env_ready(self) -> bool:
        """檢查環境就緒狀態"""
        venv_path = get_base_data_dir() / ".venv"
        return venv_path.exists() and len(list(venv_path.glob("**/site-packages/torch"))) > 0

    def is_llama_ready(self) -> bool:
        """檢查 llama-cpp-python 是否已安裝"""
        try:
            import llama_cpp
            return True
        except ImportError:
            return False

    def unload_all(self):
        """強制清空所有已註冊的模型顯存"""
        with self._lock:
            for slot, unloader in self._unloaders.items():
                try:
                    unloader()
                except Exception:
                    pass
            self._loaded_slots.clear()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

               
def get_model_manager() -> ModelManager:
    return ModelManager()
