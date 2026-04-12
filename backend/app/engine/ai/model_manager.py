"""
Model and VRAM management center (Three-Layer Architecture V6).

Responsibilities:
1. Model registration and download coordination
2. VRAM scheduling and slot management
3. Provide navigator APIs for Runtime use
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
)

logger = logging.getLogger(__name__)

class ModelManager:
    """
    Model manager singleton.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._gpu_lock = threading.Lock()
        self._loaded_slots: Set[str] = set()
        self._unloaders: Dict[str, Callable[[], None]] = {}
        logger.info("ModelManager (V5) initialized with Registry")

    @contextmanager
    def gpu_session(self):
        """VRAM lock: ensures image processing and language inference don't compete for VRAM simultaneously."""
        with self._gpu_lock:
            try:
                yield
            finally:
                # Unload all loaded models (including llama-server subprocesses)
                for slot in list(self._loaded_slots):
                    unloader = self._unloaders.get(slot)
                    if unloader:
                        try:
                            unloader()
                        except Exception as e:
                            logger.warning(f"gpu_session cleanup: failed to unload {slot}: {e}")
                self._loaded_slots.clear()
                # Force release GPU memory
                import gc
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

    def register_unloader(self, slot: str, callback: Callable[[], None]):
        """Register a model unload callback."""
        self._unloaders[slot] = callback

    def acquire(self, slot: str, required_vram_mb: int = 0) -> None:
        """Request loading a slot. Evicts other loaded slots to free VRAM."""
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
        """Mark a slot as unloaded."""
        with self._lock:
            self._loaded_slots.discard(slot)

    # ═══════════════════════════════════════════════════════
    # Navigator APIs
    # ═══════════════════════════════════════════════════════
    
    def get_model_format(self, model_id: str) -> Optional[str]:
        """
        Query the format a model belongs to.

        Returns:
            FORMAT_PKG / FORMAT_GGUF / FORMAT_PTH / None
        """
        for fmt in [FORMAT_PKG, FORMAT_GGUF, FORMAT_PTH]:
            if model_id in MODELS_REGISTRY.get(fmt, {}):
                return fmt
        return None
    
    def get_model_config(self, model_id: str, variant: Optional[str] = None) -> Optional[Dict]:
        """
        Get full model configuration.

        Returns:
            Config dict (contains repo_id, vram_mb, layers, etc.)
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
            
            # Merge spec with variant_spec
            return {
                **variant_spec,
                "layers": spec["layers"],
                "n_ctx": spec.get("n_ctx_default", spec.get("n_ctx", 4096)),
                "vram_overhead_mb": spec["vram_overhead_mb"],
            }
        
        elif fmt == FORMAT_PTH:
            # PTH: variants -> variant
            return family["variants"].get(variant) if variant else None

        return None
    
    def get_vram_requirement(self, model_id: str, variant: Optional[str] = None) -> int:
        """
        Get model VRAM requirement (MB).

        Returns:
            VRAM requirement in MB, returns 0 on failure.
        """
        config = self.get_model_config(model_id, variant)
        if not config:
            return 0
        
        # PKG/PTH formats have vram_mb directly
        if "vram_mb" in config:
            return config["vram_mb"]
        
        # GGUF format: size_mb + mmproj_size_mb + vram_overhead_mb
        if "size_mb" in config and "vram_overhead_mb" in config:
            return config["size_mb"] + config.get("mmproj_size_mb", 0) + config["vram_overhead_mb"]

        return 0
    
    def get_model_path(self, model_id: str, variant: Optional[str] = None) -> Optional[Path]:
        """
        Get the local path of a model (adapted for format-first registry).

        Args:
            model_id: Model family ID (e.g. "whisper", "qwen3", "realesrgan").
            variant: Variant (e.g. "medium", "4b:Q4_K_M", "x4plus").

        Returns:
            Model path (directory or file), None if not found.
        """
        fmt = self.get_model_format(model_id)
        if not fmt:
            logger.warning(f"Unknown model_id: {model_id}")
            return None
        
        family = MODELS_REGISTRY[fmt][model_id]
        slot = family.get("slot", "")
        models_dir = SETTINGS.path.models
        base_dir = models_dir / slot

        # PKG format (directory-based, e.g. Whisper)
        if fmt == FORMAT_PKG:
            target = base_dir / variant if variant else base_dir
            # Check key file to verify completeness
            marker = target / "model.bin"
            return target if marker.exists() else None

        # GGUF format (single-file, stored in models/{model_id}/)
        elif fmt == FORMAT_GGUF:
            config = self.get_model_config(model_id, variant)
            if not config or "filename" not in config:
                return None
            target = (models_dir / model_id) / config["filename"]
            return target if target.exists() else None

        # PTH format (single-file)
        elif fmt == FORMAT_PTH:
            if not variant:
                # Default to the first variant
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
        Unified download logic (adapted for format-first registry).

        Args:
            model_id: Model family ID.
            variant: Variant.
            on_progress: Progress callback.

        Returns:
            Downloaded path.
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
        
        # PKG format (directory snapshot, e.g. Whisper)
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
        
        # GGUF format (single or dual file: vision models with mmproj)
        elif fmt == FORMAT_GGUF:
            config = self.get_model_config(model_id, variant)
            if not config or "repo_id" not in config or "filename" not in config:
                raise ValueError(f"Invalid GGUF config for {model_id}/{variant}")

            gguf_dir = models_dir / model_id
            gguf_dir.mkdir(parents=True, exist_ok=True)

            has_mmproj = "mmproj_filename" in config

            def _prog_main(p, msg):
                if on_progress:
                    on_progress(p * (0.7 if has_mmproj else 1.0), msg)

            path = await self._async_hf_hub_download(
                repo_id=config["repo_id"],
                filename=config["filename"],
                local_dir=str(gguf_dir),
                on_progress=_prog_main,
            )

            if has_mmproj:
                def _prog_mm(p, msg):
                    if on_progress:
                        on_progress(0.7 + p * 0.3, f"[mmproj] {msg}")

                await self._async_hf_hub_download(
                    repo_id=config.get("mmproj_repo_id", config["repo_id"]),
                    filename=config["mmproj_filename"],
                    local_dir=str(gguf_dir),
                    on_progress=_prog_mm,
                )

            if on_progress:
                on_progress(1.0, "task.progress.download_complete")
            return Path(path)

        # PTH format (single file)
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
        """Async download of a HuggingFace snapshot."""
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
        """Async download of a single HuggingFace file."""
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
        """Check whether the llama-server binary exists."""
        import sys
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        return (SETTINGS.path.llama / exe_name).exists()

    def unload_all(self):
        """Force unload all registered models and free VRAM."""
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

