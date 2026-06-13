"""Waifu2x super-resolution model wrapper (ncnn-vulkan, Phase-1 de-torch).

A model wrapper (BaseWrapper subclass): owns the model lifecycle (slot, file
validation, acquire) and the waifu2x-specific CLI knowledge (its `-n <noise> -v`
flags and its per-file `done` progress line). waifu2x-ncnn-vulkan infers the
model architecture from the `-m` dir basename, so its weights live under
`models-cunet/` (registry cli_model_subdir). Execution is delegated to the binary
adapter `NcnnVulkan`. Replaced the torch/spandrel Waifu2xWrapper.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image

from app.adapters.ai.wrapper.base import BaseWrapper
from app.adapters.binary.ncnn import NcnnVulkan


class Waifu2xWrapper(BaseWrapper):
    """Waifu2x via waifu2x-ncnn-vulkan (cunet, models-cunet/scale2.0x_model)."""

    def __init__(self) -> None:
        super().__init__(slot="upscale")
        self._ncnn = NcnnVulkan("waifu2x", "waifu2x-ncnn-vulkan")

    # -- model lifecycle --
    def _load_impl(self, model_path: Any, config: dict,
                   on_progress: Optional[Callable[[float, str], None]] = None) -> Any:
        if on_progress:
            on_progress(0.4, f"task.progress.load_model|{config.get('model_id', 'waifu2x')}")
        if model_path is None:
            raise FileNotFoundError(
                f"ncnn model files for waifu2x/{config.get('variant')} not "
                f"downloaded (expected under models/{config.get('slot', 'waifu2x')}/)")
        param = Path(str(model_path))
        missing = [f for f in config["files"] if not (param.parent / f).exists()]
        if missing:
            raise FileNotFoundError(f"ncnn model files missing: {missing}")
        return {"model_dir": param.parent, "config": config}

    def _unload_impl(self) -> None:
        pass  # nothing resident: the CLI owns GPU memory per run

    @property
    def last_run_lines(self) -> list[str]:
        return self._ncnn.last_run_lines    # NFR2 device-line evidence

    # -- waifu2x-specific CLI knowledge --
    def _model_flags(self, cfg: dict) -> list[str]:
        # -v makes the CLI print a per-file `<in> -> <out> done` line we count.
        return ["-n", str(cfg["cli_noise"]), "-v"]

    def _progress(self, line: str, state: dict, base_done: int,
                  total_frames: int) -> Optional[tuple[float, str]]:
        if "done" not in line:                       # waifu2x prints no percentages
            return None
        state["done"] = state.get("done", 0) + 1
        n = base_done + state["done"]
        frac = n / max(total_frames, 1)
        return frac, f"task.progress.upscale_frame|{n}|{total_frames}"

    # -- public inference API (self-acquiring) --
    def enhance(self, image: Image.Image, model_id: str = "", scale: int = 0,
                on_progress: Optional[Callable[[float, str], None]] = None) -> Image.Image:
        """PIL → PIL. `model_id` = variant (service convention); native scale applies."""
        with self.acquire(model_id="waifu2x", variant=model_id or None, on_progress=on_progress):
            cfg = self._model["config"]
            return self._ncnn.upscale_image(
                image, self._model["model_dir"], cfg["scale"],
                self._model_flags(cfg), self._progress, on_progress)

    def enhance_dir(self, in_dir: Path, out_dir: Path, total_frames: int,
                    model_id: str = "", *, base_done: int = 0, chunk_total: int = 0,
                    on_progress: Optional[Callable[[float, str], None]] = None) -> None:
        """Directory mode for ONE CHUNK of frames (caller batches)."""
        with self.acquire(model_id="waifu2x", variant=model_id or None, on_progress=on_progress):
            cfg = self._model["config"]
            self._ncnn.upscale_dir(
                in_dir, out_dir, self._model["model_dir"], cfg["scale"],
                self._model_flags(cfg), total_frames, base_done=base_done,
                chunk_total=chunk_total, progress_parser=self._progress, on_progress=on_progress)
