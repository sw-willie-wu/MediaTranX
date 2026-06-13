"""ncnn-vulkan upscaler CLI adapter — the thin binary wrapper (sibling of
ffmpeg.py / ytdlp.py / llama_server.py).

Owns everything that is about *running an ncnn-vulkan upscaler exe* and nothing
about a specific model or the model lifecycle: exe-path resolution
(bin/ncnn/<tool>/), the `-i/-o/-m/-s/-f/-g` arg skeleton, the temp-PNG round-trip
for single images, the CLIs' directory mode in CHUNKS for frame batches, and the
output-existence check. Safe one-shot subprocess (deadlock-free pump, Job-Object
orphan-kill, NTSTATUS crash classification) is delegated to CliSidecar.

Generic over the model: the caller (a model wrapper) passes the model-selecting
flags (`-n <name>` vs `-n <noise> -v`) and a progress parser. Verified CLI quirks
(2026-06-12, RTX 3080): realesrgan prints `NN.NN%` per tile on stderr and never
`100.00%`; waifu2x prints a `done` line per file on stdout; CliSidecar merges both
streams; `-g -1` = CPU mode when no Vulkan loader is present (FR5).
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from app.adapters.binary.sidecar import CliSidecar, SidecarError

logger = logging.getLogger(__name__)

_SINGLE_TIMEOUT_S = 600.0
_CHUNK_TIMEOUT_S = 1800.0

# A progress parser maps one merged-output line to (job_fraction, i18n_message),
# or None. `state` persists across the run so a parser can accumulate.
ProgressParser = Callable[[str, dict, int, int], Optional[tuple[float, str]]]


class NcnnVulkan:
    """Runs one ncnn-vulkan upscaler exe (e.g. realesrgan-ncnn-vulkan)."""

    def __init__(self, tool: str, exe_name: str):
        self.tool = tool            # bin/ncnn/<tool>/ subdir
        self.exe_name = exe_name    # exe stem, e.g. "realesrgan-ncnn-vulkan"
        self.last_run_lines: list[str] = []   # per-run NFR2 device-line evidence

    def exe_path(self) -> Path:
        from app.init.configs import SETTINGS  # lazy: binary-module convention
        name = self.exe_name + (".exe" if sys.platform == "win32" else "")
        p = SETTINGS.path.ncnn / self.tool / name
        if p.exists():
            return p
        raise FileNotFoundError(
            f"{name} not installed (expected {p}); run setup / reinstall AI env")

    def _build_args(self, in_path: Path, out_path: Path, model_dir: Path,
                    scale: int, model_flags: list[str]) -> list[str]:
        from app.adapters.device import has_vulkan
        args = ["-i", str(in_path), "-o", str(out_path), "-m", str(model_dir),
                "-s", str(scale), "-f", "png", *model_flags]
        if not has_vulkan():
            logger.warning(f"no Vulkan loader; {self.tool} ncnn running in CPU mode (-g -1)")
            args += ["-g", "-1"]
        return args

    def _run(self, in_path: Path, out_path: Path, model_dir: Path, scale: int,
             model_flags: list[str], progress_parser: Optional[ProgressParser],
             on_progress: Optional[Callable[[float, str], None]],
             total_frames: int, base_done: int, timeout: float) -> None:
        self.last_run_lines = []
        state: dict = {}

        def _on_line(line: str) -> None:
            logger.debug(f"[{self.tool}] {line}")
            self.last_run_lines.append(line)
            if len(self.last_run_lines) > 200:
                self.last_run_lines.pop(0)
            if on_progress is None or progress_parser is None:
                return
            result = progress_parser(line, state, base_done, total_frames)
            if result is not None:
                frac, msg = result
                on_progress(1.0 + min(frac, 0.999), msg)   # inference band: [1.0, 2.0)

        sc = CliSidecar(exe=str(self.exe_path()), on_line=_on_line)
        sc.run(self._build_args(in_path, out_path, model_dir, scale, model_flags),
               timeout=timeout)
        if out_path.is_file() or (out_path.is_dir() and any(out_path.iterdir())):
            return
        raise SidecarError(self.exe_name, 0,
                           f"CLI exited 0 but produced no output at {out_path}")

    # ── high-level helpers used by the model wrappers ───────────────────────
    def upscale_image(self, image: Image.Image, model_dir: Path, scale: int,
                      model_flags: list[str], progress_parser: Optional[ProgressParser] = None,
                      on_progress: Optional[Callable[[float, str], None]] = None) -> Image.Image:
        """PIL → PIL via a temp-PNG round-trip (single image, native scale)."""
        with tempfile.TemporaryDirectory(prefix="ncnn_sr_") as td:
            in_p, out_p = Path(td) / "in.png", Path(td) / "out.png"
            image.save(in_p, "PNG")
            self._run(in_p, out_p, model_dir, scale, model_flags, progress_parser,
                      on_progress, total_frames=1, base_done=0, timeout=_SINGLE_TIMEOUT_S)
            out = Image.open(out_p)
            out.load()                  # fully read before the tempdir vanishes
            return out

    def upscale_dir(self, in_dir: Path, out_dir: Path, model_dir: Path, scale: int,
                    model_flags: list[str], total_frames: int, *, base_done: int = 0,
                    chunk_total: int = 0, progress_parser: Optional[ProgressParser] = None,
                    on_progress: Optional[Callable[[float, str], None]] = None) -> None:
        """Directory mode for ONE CHUNK of frames (caller batches; one spawn per
        chunk). `base_done`/`total_frames` position this chunk within the whole
        job; `chunk_total` = frames in THIS chunk (output-count check)."""
        chunk_total = chunk_total or total_frames
        out_dir.mkdir(parents=True, exist_ok=True)
        self._run(in_dir, out_dir, model_dir, scale, model_flags, progress_parser,
                  on_progress, total_frames=total_frames, base_done=base_done,
                  timeout=_CHUNK_TIMEOUT_S)
        produced = len(list(out_dir.glob("*.png")))
        if produced < chunk_total:
            raise SidecarError(self.exe_name, 0,
                               f"directory mode produced {produced}/{chunk_total} frames")
