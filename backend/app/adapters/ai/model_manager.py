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
from typing import Optional, Dict, Callable, Set, Any

from app.init.configs import SETTINGS
from .registry import (
    MODELS_REGISTRY,
    FORMAT_PKG,
    FORMAT_GGUF,
    FORMAT_PTH,
)

logger = logging.getLogger(__name__)

# GPU inference gate 逾時（秒）：task 類等得起（聊天生成必然終止）、agent 類快回
# 友善忙碌訊息。測試可 monkeypatch。
GATE_TIMEOUTS: Dict[str, float] = {"task": 600.0, "agent": 30.0}


class ModelManager:
    """
    Model manager singleton.
    """
    def __init__(self):
        self._lock = threading.RLock()
        # GPU inference gate（spec B2.5）:全域、每執行緒可重入。取得於 acquire()
        # 開頭（evict 前）、釋放於 yield 結束——所有本地 AI 推論全域序列化。
        # Condition 綁 _lock:wait() 原子釋放鎖,unpin 時 notify。
        self._gate_cond = threading.Condition(self._lock)
        self._gate_owner: Optional[int] = None   # thread ident
        self._gate_depth = 0
        self._loaded_slots: Set[str] = set()
        self._unloaders: Dict[str, Callable[[], None]] = {}
        self._runtimes: Dict[str, Any] = {}
        # slot → zero-arg callable returning a wrapper instance (DI singleton).
        self._runtime_providers: Dict[str, Callable[[], Any]] = {}
        # slot → callable(model_id) returning a wrapper instance (fresh per model_id).
        self._dispatchers: Dict[str, Callable[[str], Any]] = {}
        logger.info("ModelManager (V6) initialized with Registry")

    def _acquire_gate(self, gate_class: str) -> bool:
        """Take the global GPU gate（每執行緒可重入）。回傳 False = 逾時。"""
        import time
        timeout = GATE_TIMEOUTS.get(gate_class, GATE_TIMEOUTS["task"])
        me = threading.get_ident()
        with self._gate_cond:
            if self._gate_owner == me:
                self._gate_depth += 1
                return True
            deadline = time.monotonic() + timeout
            while self._gate_owner is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._gate_cond.wait(remaining)
            self._gate_owner = me
            self._gate_depth = 1
            return True

    def _release_gate(self) -> None:
        with self._gate_cond:
            if self._gate_owner != threading.get_ident():
                logger.warning("GPU gate release by non-owner thread ignored")
                return
            self._gate_depth -= 1
            if self._gate_depth == 0:
                self._gate_owner = None
                self._gate_cond.notify_all()

    @contextmanager
    def gpu_session(self, gate_class: str = "task"):
        """GPU 會話：取全域 inference gate（取代舊 _gpu_lock），結束時卸載所有模型。"""
        from app.handler.exceptions import ModelBusyError
        if not self._acquire_gate(gate_class):
            raise ModelBusyError(
                f"GPU busy: gpu_session wait exceeded {GATE_TIMEOUTS.get(gate_class)}s"
            )
        try:
            yield
        finally:
            try:
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
            finally:
                self._release_gate()

    def register_unloader(self, slot: str, callback: Callable[[], None]):
        """Register a model unload callback."""
        self._unloaders[slot] = callback

    def register_runtime(self, runtime: Any) -> None:
        """Directly register a runtime instance.

        Used by container for pre-registered slots (LlmWrapper). Attaches
        `runtime._model_manager = self` so `BaseWrapper.acquire()` can delegate
        back here.
        """
        self._runtimes[runtime.slot] = runtime
        self._unloaders[runtime.slot] = runtime.unload
        runtime._model_manager = self

    def register_runtime_provider(self, slot: str, provider: Callable[[], Any]) -> None:
        """Register a zero-arg factory for a non-dispatcher slot.

        Called by `init_container` at startup. `provider` typically wraps a
        DI singleton so all consumers share the same wrapper instance.
        """
        self._runtime_providers[slot] = provider

    def register_dispatcher(self, slot: str, dispatcher: Callable[[str], Any]) -> None:
        """Register a per-model_id factory for a dispatcher slot.

        `dispatcher(model_id)` returns a wrapper instance for that family.
        Different model_ids map to different wrapper instances (the manager
        caches the currently-loaded one in `_runtimes[slot]`).
        """
        self._dispatchers[slot] = dispatcher

    @contextmanager
    def acquire(
        self,
        slot: str,
        model_id: str,
        variant: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        gate_class: str = "task",
    ):
        """Acquire a runtime loaded with the requested model/variant.

        GPU gate 取得於 evict 前（否則 direct-acquire 路徑會先殺掉別人推論中
        的模型才排隊）、釋放於 yield 結束（try/finally，載入失敗不洩漏）。
        _lock 只護 evict/load；yield（推論）在 _lock 外、gate 內。
        """
        from app.handler.exceptions import ModelBusyError
        if not self._acquire_gate(gate_class):
            raise ModelBusyError(
                f"GPU busy: slot {slot!r} gate wait exceeded "
                f"{GATE_TIMEOUTS.get(gate_class, GATE_TIMEOUTS['task'])}s"
            )
        try:
            with self._lock:
                runtime = self._ensure_runtime(slot, model_id)

                config_key = f"{model_id}:{variant}"
                needs_reload = (
                    not runtime.is_loaded()
                    or (runtime.get_current_config() or {}).get("_key") != config_key
                )

                if needs_reload:
                    # Evict other slots
                    for other in list(self._loaded_slots):
                        if other == slot:
                            continue
                        unloader = self._unloaders.get(other)
                        if unloader:
                            try:
                                unloader()
                                logger.info(f"Evicted slot: {other}")
                            except Exception as e:
                                logger.error(f"Failed to evict {other}: {e}")
                    self._loaded_slots.clear()

                    # CUDA cache clear
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass

                    # Load
                    if runtime.is_loaded():
                        runtime.unload()
                    model_path, config = runtime._resolve_model_path(model_id, variant, self)
                    config["_key"] = config_key
                    runtime.load(model_path, config, on_progress)

                    self._loaded_slots.add(slot)

            # Yield outside _lock so slot state checks aren't blocked; gate held.
            yield runtime
        finally:
            self._release_gate()

    def _ensure_runtime(self, slot: str, model_id: Optional[str] = None) -> Any:
        """Return the runtime instance for (slot, model_id).

        Three cases:
        1. Slot has a dispatcher (e.g. `upscale`): instantiate via dispatcher,
           swap cached instance when model_id changes.
        2. Slot has a runtime provider (e.g. `whisper`, `llm`): one-shot init from
           the provider (typically a DI singleton), cache for lifetime of the process.
        3. Pre-registered runtime (registered directly via `register_runtime` —
           tests only): always return the cached instance.
        """
        existing = self._runtimes.get(slot)

        dispatcher = self._dispatchers.get(slot)
        if dispatcher is not None:
            needs_swap = (
                model_id is not None
                and existing is not None
                and getattr(existing, "_dispatched_model_id", None) != model_id
            )
            if existing is None or needs_swap:
                if existing is not None:
                    existing.unload()
                runtime = dispatcher(model_id)
                runtime._dispatched_model_id = model_id
                runtime._model_manager = self
                self._runtimes[slot] = runtime
                self._unloaders[slot] = runtime.unload
                return runtime
            return existing

        provider = self._runtime_providers.get(slot)
        if provider is not None:
            if existing is None:
                runtime = provider()
                runtime._model_manager = self
                self._runtimes[slot] = runtime
                self._unloaders[slot] = runtime.unload
                return runtime
            return existing

        if existing is not None:
            return existing  # pre-registered directly via register_runtime (tests only)
        raise KeyError(f"Unknown runtime slot: {slot!r}")

    def _acquire_lock(self, slot: str, required_vram_mb: int = 0) -> None:
        """Legacy VRAM-only lock (pre-B-clean). Retained private until all callers
        migrate to the new acquire(slot, model_id, variant, on_progress)."""
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

