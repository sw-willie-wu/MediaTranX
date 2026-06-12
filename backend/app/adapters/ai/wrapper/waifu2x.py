"""Waifu2x super-resolution wrapper (ncnn-vulkan CLI, Phase-1 de-torch).

Concrete NcnnUpscaleWrapper subclass: implements how waifu2x-ncnn-vulkan is
driven. The CLI infers the model architecture from the `-m` dir basename, so its
weights live under `models-cunet/` (registry cli_model_subdir). Replaced the
torch/spandrel Waifu2xWrapper when SR moved off PyTorch.
"""
from __future__ import annotations

from typing import Optional

from app.adapters.ai.wrapper.ncnn_upscale import NcnnUpscaleWrapper


class Waifu2xWrapper(NcnnUpscaleWrapper):
    """Waifu2x via waifu2x-ncnn-vulkan (cunet, models-cunet/scale2.0x_model)."""

    family = "waifu2x"
    exe_name = "waifu2x-ncnn-vulkan"

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
