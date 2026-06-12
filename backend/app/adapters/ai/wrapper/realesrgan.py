"""Real-ESRGAN super-resolution wrapper (ncnn-vulkan CLI, Phase-1 de-torch).

Concrete NcnnUpscaleWrapper subclass: implements how realesrgan-ncnn-vulkan is
driven. Replaced the torch/spandrel RealESRGANWrapper when SR moved off PyTorch.
"""
from __future__ import annotations

import re
from typing import Optional

from app.adapters.ai.wrapper.ncnn_upscale import NcnnUpscaleWrapper

# realesrgan prints `NN.NN%` per tile and emits exactly ONE 0.00% line per frame.
_PERCENT_RE = re.compile(r"^(\d{1,3}\.\d{2})%")


class RealESRGANWrapper(NcnnUpscaleWrapper):
    """Real-ESRGAN via realesrgan-ncnn-vulkan (x4plus / x4plus-anime / animevideov3)."""

    family = "realesrgan"
    exe_name = "realesrgan-ncnn-vulkan"

    def _model_flags(self, cfg: dict) -> list[str]:
        # picks the model by name; -s already set by the base from cfg["scale"].
        return ["-n", cfg["cli_model_name"]]

    def _progress(self, line: str, state: dict, base_done: int,
                  total_frames: int) -> Optional[tuple[float, str]]:
        m = _PERCENT_RE.match(line.strip())
        if not m:
            return None
        # A fresh frame restarts the counter at 0.00% (dir mode interleaves
        # frames but each still prints 0.00% once) and it NEVER prints 100.00%,
        # so count 0.00% lines as frames entered; the chunk's output-count check
        # is the real completion gate.
        pct = float(m.group(1)) / 100.0
        if pct == 0.0:
            state["started"] = state.get("started", 0) + 1
        state["cur"] = min(pct, 0.999)
        advanced = max(state.get("started", 0) - 1, 0) + state["cur"]
        frac = (base_done + min(advanced, total_frames)) / max(total_frames, 1)
        return frac, "task.progress.upscale_running"
