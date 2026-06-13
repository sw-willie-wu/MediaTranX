"""Real-ESRGAN super-resolution model wrapper (ncnn-vulkan, Phase-1 de-torch).

A model wrapper (BaseWrapper subclass): owns the model lifecycle (slot, file
validation, acquire) and the realesrgan-specific CLI knowledge (its `-n <name>`
flag and its `NN.NN%` progress stream). The actual exe execution is delegated to
the binary adapter `NcnnVulkan`. Replaced the torch/spandrel RealESRGANWrapper.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image

from app.adapters.ai.wrapper.base import BaseWrapper
from app.adapters.binary.ncnn import NcnnVulkan

# realesrgan prints `NN.NN%` per tile and emits exactly ONE 0.00% line per frame.
_PERCENT_RE = re.compile(r"^(\d{1,3}\.\d{2})%")


class RealESRGANWrapper(BaseWrapper):
    """Real-ESRGAN via realesrgan-ncnn-vulkan (x4plus / x4plus-anime / animevideov3)."""

    def __init__(self) -> None:
        super().__init__(slot="upscale")
        self._ncnn = NcnnVulkan("realesrgan", "realesrgan-ncnn-vulkan")

    # -- model lifecycle --
    def _load_impl(self, model_path: Any, config: dict,
                   on_progress: Optional[Callable[[float, str], None]] = None) -> Any:
        if on_progress:
            on_progress(0.4, f"task.progress.load_model|{config.get('model_id', 'realesrgan')}")
        if model_path is None:
            raise FileNotFoundError(
                f"ncnn model files for realesrgan/{config.get('variant')} not "
                f"downloaded (expected under models/{config.get('slot', 'realesrgan')}/)")
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

    # -- realesrgan-specific CLI knowledge --
    def _model_flags(self, cfg: dict) -> list[str]:
        return ["-n", cfg["cli_model_name"]]

    def _progress(self, line: str, state: dict, base_done: int,
                  total_frames: int) -> Optional[tuple[float, str]]:
        m = _PERCENT_RE.match(line.strip())
        if not m:
            return None
        # A fresh frame restarts at 0.00% (dir mode interleaves but each frame
        # prints 0.00% once) and the CLI NEVER prints 100.00%, so count 0.00%
        # lines as frames entered; the output-count check is the real gate.
        pct = float(m.group(1)) / 100.0
        if pct == 0.0:
            state["started"] = state.get("started", 0) + 1
        state["cur"] = min(pct, 0.999)
        advanced = max(state.get("started", 0) - 1, 0) + state["cur"]
        frac = (base_done + min(advanced, total_frames)) / max(total_frames, 1)
        return frac, "task.progress.upscale_running"

    # -- public inference API (self-acquiring) --
    def enhance(self, image: Image.Image, model_id: str = "", scale: int = 0,
                on_progress: Optional[Callable[[float, str], None]] = None) -> Image.Image:
        """PIL → PIL. `model_id` = variant (service convention); native scale applies."""
        with self.acquire(model_id="realesrgan", variant=model_id or None, on_progress=on_progress):
            cfg = self._model["config"]
            return self._ncnn.upscale_image(
                image, self._model["model_dir"], cfg["scale"],
                self._model_flags(cfg), self._progress, on_progress)

    def enhance_dir(self, in_dir: Path, out_dir: Path, total_frames: int,
                    model_id: str = "", *, base_done: int = 0, chunk_total: int = 0,
                    on_progress: Optional[Callable[[float, str], None]] = None) -> None:
        """Directory mode for ONE CHUNK of frames (caller batches)."""
        with self.acquire(model_id="realesrgan", variant=model_id or None, on_progress=on_progress):
            cfg = self._model["config"]
            self._ncnn.upscale_dir(
                in_dir, out_dir, self._model["model_dir"], cfg["scale"],
                self._model_flags(cfg), total_frames, base_done=base_done,
                chunk_total=chunk_total, progress_parser=self._progress, on_progress=on_progress)
