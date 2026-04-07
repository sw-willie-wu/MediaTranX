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

from app.init.configs import SETTINGS
from .registry import (
    MODELS_REGISTRY,
    FORMAT_PKG,
    FORMAT_GGUF,
    FORMAT_PTH,
    FORMAT_VLM,
)

logger = logging.getLogger(__name__)

class ModelManager:
    """
    模型管理器單例
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._gpu_lock = threading.Lock()
        self._loaded_slots: Set[str] = set()
        self._unloaders: Dict[str, Callable[[], None]] = {}
        logger.info("ModelManager (V5) initialized with Registry")

    @contextmanager
    def gpu_session(self):
        """顯存鎖：確保影像處理與語言推理不會同時搶奪顯存"""
        with self._gpu_lock:
            try:
                yield
            finally:
                # 卸載所有已載入的模型（含 llama-server subprocess）
                for slot in list(self._loaded_slots):
                    unloader = self._unloaders.get(slot)
                    if unloader:
                        try:
                            unloader()
                        except Exception as e:
                            logger.warning(f"gpu_session cleanup: failed to unload {slot}: {e}")
                self._loaded_slots.clear()
                # 強制釋放 GPU 記憶體
                import gc
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

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
            except Exception:
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
            FORMAT_PKG / FORMAT_GGUF / FORMAT_PTH / FORMAT_VLM / None
        """
        for fmt in [FORMAT_PKG, FORMAT_GGUF, FORMAT_PTH, FORMAT_VLM]:
            if model_id in MODELS_REGISTRY.get(fmt, {}):
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
        
        if fmt == FORMAT_PKG:
            # Whisper: variants -> variant
            return family["variants"].get(variant) if variant else None
        
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

        elif fmt == FORMAT_VLM:
            # VLM: specs -> size -> variants -> quant（與 GGUF 相同結構，但含 mmproj 欄位）
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

            return {
                **variant_spec,
                "layers": spec["layers"],
                "n_ctx": spec["n_ctx"],
                "vram_overhead_mb": spec["vram_overhead_mb"],
            }

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
        
        # PKG/PTH 格式直接有 vram_mb
        if "vram_mb" in config:
            return config["vram_mb"]
        
        # GGUF / VLM 格式：size_mb + mmproj_size_mb + vram_overhead_mb
        if "size_mb" in config and "vram_overhead_mb" in config:
            return config["size_mb"] + config.get("mmproj_size_mb", 0) + config["vram_overhead_mb"]

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
        models_dir = SETTINGS.path.models
        base_dir = models_dir / slot

        # PKG 格式（目錄型，如 Whisper）
        if fmt == FORMAT_PKG:
            target = base_dir / variant if variant else base_dir
            # 檢查關鍵檔案判斷完整性
            marker = target / "model.bin"
            return target if marker.exists() else None

        # GGUF 格式（單檔型，存放於 models/{model_id}/）
        elif fmt == FORMAT_GGUF:
            config = self.get_model_config(model_id, variant)
            if not config or "filename" not in config:
                return None
            target = (models_dir / model_id) / config["filename"]
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

        # VLM 格式（單檔型，主模型；mmproj 由 runtime 另行解析）
        elif fmt == FORMAT_VLM:
            config = self.get_model_config(model_id, variant)
            if not config or "filename" not in config:
                return None
            target = base_dir / config["filename"]
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
        models_dir = SETTINGS.path.models
        base_dir = models_dir / slot
        base_dir.mkdir(parents=True, exist_ok=True)
        
        if on_progress:
            on_progress(0.1, f"task.progress.download_start|{model_id}")
        
        # PKG 格式（目錄型快照，如 Whisper）
        if fmt == FORMAT_PKG:
            config = self.get_model_config(model_id, variant)
            if not config or "repo_id" not in config:
                raise ValueError(f"Invalid PKG config for {model_id}/{variant}")
            
            local_dir = base_dir / variant
            path = await self._async_snapshot_download(
                repo_id=config["repo_id"],
                local_dir=str(local_dir),
                on_progress=on_progress
            )
            return Path(path)
        
        # VLM 格式（雙檔：主模型 + mmproj）
        elif fmt == FORMAT_VLM:
            config = self.get_model_config(model_id, variant)
            if not config or "repo_id" not in config or "filename" not in config:
                raise ValueError(f"Invalid VLM config for {model_id}/{variant}")

            # 下載主模型
            def _prog_main(p, msg):
                if on_progress:
                    on_progress(p * 0.7, msg)

            path = await self._async_hf_hub_download(
                repo_id=config["repo_id"],
                filename=config["filename"],
                local_dir=str(base_dir),
                on_progress=_prog_main,
            )

            # 下載 mmproj（視覺編碼器）
            if "mmproj_filename" in config:
                def _prog_mm(p, msg):
                    if on_progress:
                        on_progress(0.7 + p * 0.3, f"[mmproj] {msg}")

                await self._async_hf_hub_download(
                    repo_id=config.get("mmproj_repo_id", config["repo_id"]),
                    filename=config["mmproj_filename"],
                    local_dir=str(base_dir),
                    on_progress=_prog_mm,
                )

            if on_progress:
                on_progress(1.0, "task.progress.download_complete")
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
            on_progress(1.0, "task.progress.download_complete")
        
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
            on_progress(1.0, "task.progress.download_complete")
        
        return path

    def is_llama_ready(self) -> bool:
        """檢查 llama-server 二進位是否存在"""
        import sys
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        return (SETTINGS.path.llama / exe_name).exists()

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
            except Exception:
                pass

