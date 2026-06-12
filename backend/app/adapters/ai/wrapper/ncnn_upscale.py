"""ncnn-vulkan CLI upscaler wrapper (Real-ESRGAN / waifu2x / Real-CUGAN).

BaseWrapper subclass with slot="upscale" (dispatcher contract) that shells out
to the official ncnn-vulkan CLIs via CliSidecar — same wrapper↔binary layering
as LlmWrapper↔LlamaServer. Single images round-trip through temp PNGs; frame
batches use the CLIs' directory mode in CHUNKS (one spawn per chunk amortizes
Vulkan warmup while bounding temp disk).

Verified CLI quirks handled here (2026-06-12):
- realesrgan prints `NN.NN%` to stderr, restarting per image in directory mode
  → progress ACCUMULATES (done + pct/100)/total; waifu2x/realcugan print no
  percentages → `-v` done-lines are counted instead.
- realesrgan can exit 0 on decode failure → output existence is always checked.
- `-g -1` = CPU mode (used when no Vulkan loader is present; FR5).
"""
from __future__ import annotations

import logging
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image

from app.adapters.ai.wrapper.base import BaseWrapper
from app.adapters.binary.sidecar_base import CliSidecar, SidecarError

logger = logging.getLogger(__name__)

_PERCENT_RE = re.compile(r"^(\d{1,3}\.\d{2})%")
# Keyed by the registry's `exe_tool` field; dir name == tool name == exe stem.
_EXE_NAMES = {
    "realesrgan": "realesrgan-ncnn-vulkan",
    "waifu2x": "waifu2x-ncnn-vulkan",
    "realcugan": "realcugan-ncnn-vulkan",
}
_SINGLE_TIMEOUT_S = 600.0
_CHUNK_TIMEOUT_S = 1800.0


def _exe_path(exe_tool: str) -> Path:
    from app.init.configs import SETTINGS  # lazy: wrapper-module convention
    name = _EXE_NAMES[exe_tool] + (".exe" if sys.platform == "win32" else "")
    p = SETTINGS.path.ncnn / exe_tool / name
    if p.exists():
        return p
    raise FileNotFoundError(
        f"{name} not installed (expected {p}); run setup / reinstall AI env")


class NcnnUpscaleWrapper(BaseWrapper):
    """One instance per family; dispatched under the shared 'upscale' slot."""

    def __init__(self, family: str):
        super().__init__(slot="upscale")
        self.family = family
        self.last_run_lines: list[str] = []

    def _load_impl(self, model_path: Any, config: dict,
                   on_progress: Optional[Callable[[float, str], None]] = None) -> Any:
        if on_progress:
            on_progress(0.4, f"task.progress.load_model|{config.get('model_id', self.family)}")
        if model_path is None:
            # get_model_path returns None when files are absent — name the real
            # location instead of degrading to a cwd-relative check.
            raise FileNotFoundError(
                f"ncnn model files for {self.family}/{config.get('variant')} not "
                f"downloaded (expected under models/{config.get('slot', self.family)}/)")
        param = Path(str(model_path))
        missing = [f for f in config["files"] if not (param.parent / f).exists()]
        if missing:
            raise FileNotFoundError(f"ncnn model files missing: {missing}")
        return {"exe": _exe_path(config["exe_tool"]), "model_dir": param.parent, "config": config}

    def _unload_impl(self) -> None:
        pass  # nothing resident: the CLI owns GPU memory per run

    # -- CLI assembly ---------------------------------------------------------

    def _build_args(self, in_path: Path, out_path: Path) -> list[str]:
        from app.adapters.device import has_vulkan
        cfg = self._model["config"]
        args = ["-i", str(in_path), "-o", str(out_path),
                "-m", str(self._model["model_dir"]),
                "-s", str(cfg["scale"]), "-f", "png"]
        if "cli_model_name" in cfg:                      # realesrgan
            args += ["-n", cfg["cli_model_name"]]
        else:                                            # waifu2x / realcugan
            args += ["-n", str(cfg["cli_noise"]), "-v"]
        if not has_vulkan():
            logger.warning(f"no Vulkan loader; {self.family} ncnn running in CPU mode (-g -1)")
            args += ["-g", "-1"]
        return args

    def _run_cli(self, in_path: Path, out_path: Path,
                 on_progress: Optional[Callable[[float, str], None]],
                 total_frames: int, base_done: int, timeout: float) -> None:
        self.last_run_lines = []               # per-run NFR2 evidence (no stale carryover)
        state = {"done": 0}

        def _on_line(line: str) -> None:
            logger.debug(f"[{self.family}] {line}")
            self.last_run_lines.append(line)
            if len(self.last_run_lines) > 200:
                self.last_run_lines.pop(0)
            if on_progress is None:
                return
            m = _PERCENT_RE.match(line.strip())
            if m:
                # realesrgan restarts 0→100 per image; "100.00%" is the only
                # reliable per-image completion marker (dip-detection misses
                # untiled frames that print a single 100.00% line).
                pct = float(m.group(1)) / 100.0
                if pct >= 1.0:
                    state["done"] += 1
                cur = min(pct, 0.999) if pct < 1.0 else 0.0
                frac = (base_done + state["done"] + cur) / max(total_frames, 1)
                on_progress(1.0 + min(frac, 0.999), "task.progress.upscale_running")
            elif "done" in line:                   # waifu2x/realcugan -v per-file line
                state["done"] += 1
                frac = (base_done + state["done"]) / max(total_frames, 1)
                on_progress(1.0 + min(frac, 0.999),
                            f"task.progress.upscale_frame|{base_done + state['done']}|{total_frames}")

        sc = CliSidecar(exe=str(self._model["exe"]), on_line=_on_line)
        sc.run(self._build_args(in_path, out_path), timeout=timeout)
        if out_path.is_file() or (out_path.is_dir() and any(out_path.iterdir())):
            return
        raise SidecarError(str(self._model["exe"]), 0,
                           f"CLI exited 0 but produced no output at {out_path}")

    # -- public inference API (self-acquiring, like the torch-era wrappers) ----

    def enhance(self, image: Image.Image, model_id: str = "", scale: int = 0,
                on_progress: Optional[Callable[[float, str], None]] = None) -> Image.Image:
        """PIL → PIL. `model_id` = variant (service convention); native scale applies."""
        with self.acquire(model_id=self.family, variant=model_id or None,
                          on_progress=on_progress):
            with tempfile.TemporaryDirectory(prefix="ncnn_sr_") as td:
                in_p, out_p = Path(td) / "in.png", Path(td) / "out.png"
                image.save(in_p, "PNG")
                self._run_cli(in_p, out_p, on_progress, total_frames=1,
                              base_done=0, timeout=_SINGLE_TIMEOUT_S)
                out = Image.open(out_p)
                out.load()                  # fully read before the tempdir vanishes
                return out

    def enhance_dir(self, in_dir: Path, out_dir: Path, total_frames: int,
                    model_id: str = "", *, base_done: int = 0, chunk_total: int = 0,
                    on_progress: Optional[Callable[[float, str], None]] = None) -> None:
        """Directory mode for ONE CHUNK of frames (caller batches; one spawn per
        chunk). `base_done`/`total_frames` position this chunk's progress within
        the whole job; `chunk_total` = frames in THIS chunk (output count check)."""
        chunk_total = chunk_total or total_frames
        with self.acquire(model_id=self.family, variant=model_id or None,
                          on_progress=on_progress):
            out_dir.mkdir(parents=True, exist_ok=True)
            self._run_cli(in_dir, out_dir, on_progress, total_frames=total_frames,
                          base_done=base_done, timeout=_CHUNK_TIMEOUT_S)
            produced = len(list(out_dir.glob("*.png")))
            if produced < chunk_total:
                raise SidecarError(str(self._model["exe"]), 0,
                                   f"directory mode produced {produced}/{chunk_total} frames")
