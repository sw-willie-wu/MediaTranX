"""Shared base for the ncnn-vulkan CLI upscalers.

ABSTRACT base (one CONCRETE subclass per model — RealESRGANWrapper /
Waifu2xWrapper), mirroring the PthWrapper→per-model pattern. The base owns the
machinery every ncnn upscaler shares — temp-PNG round-trip for single images,
the CLIs' directory mode in CHUNKS for frame batches (one spawn per chunk
amortizes Vulkan warmup while bounding temp disk), the CliSidecar wiring (same
wrapper↔binary layering as LlmWrapper↔LlamaServer), output-existence check, CPU
fallback (`-g -1`, FR5), and the inference-band progress wrapping.

Each MODEL declares its binary (`exe_name`) and IMPLEMENTS the two things that
genuinely differ between CLIs:
  - `_model_flags(cfg)`  — the flags that pick the model (`-n <name>` vs
                           `-n <noise> -v`),
  - `_progress(line, …)` — how that CLI's output maps to a progress fraction
                           (realesrgan's `NN.NN%` tiles vs waifu2x's `done`
                           lines).
No model-type branching lives in the base.
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image

from app.adapters.ai.wrapper.base import BaseWrapper
from app.adapters.binary.sidecar_base import CliSidecar, SidecarError

logger = logging.getLogger(__name__)

_SINGLE_TIMEOUT_S = 600.0
_CHUNK_TIMEOUT_S = 1800.0


class NcnnUpscaleWrapper(BaseWrapper):
    """Abstract base — use a per-model subclass (sets `family` + `exe_name` and
    implements `_model_flags` / `_progress`). All run under the 'upscale' slot."""

    family: str = ""      # subclass: e.g. "realesrgan"
    exe_name: str = ""    # subclass: e.g. "realesrgan-ncnn-vulkan"

    def __init__(self) -> None:
        super().__init__(slot="upscale")
        if not self.family or not self.exe_name:
            raise TypeError(
                f"{type(self).__name__} must set `family` and `exe_name` — "
                "NcnnUpscaleWrapper is abstract; use a per-model subclass "
                "(RealESRGANWrapper / Waifu2xWrapper)")
        self.last_run_lines: list[str] = []

    # ── per-model implementation hooks ──────────────────────────────────────
    def _model_flags(self, cfg: dict) -> list[str]:
        """CLI flags that select the model from the registry config."""
        raise NotImplementedError

    def _progress(self, line: str, state: dict, base_done: int,
                  total_frames: int) -> Optional[tuple[float, str]]:
        """Map one merged-output line to (job_fraction, i18n_message), or None
        when the line carries no progress. `state` persists across the run."""
        raise NotImplementedError

    # ── shared mechanics ────────────────────────────────────────────────────
    def _exe_path(self) -> Path:
        from app.init.configs import SETTINGS  # lazy: wrapper-module convention
        name = self.exe_name + (".exe" if sys.platform == "win32" else "")
        p = SETTINGS.path.ncnn / self.family / name
        if p.exists():
            return p
        raise FileNotFoundError(
            f"{name} not installed (expected {p}); run setup / reinstall AI env")

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
        return {"exe": self._exe_path(), "model_dir": param.parent, "config": config}

    def _unload_impl(self) -> None:
        pass  # nothing resident: the CLI owns GPU memory per run

    def _build_args(self, in_path: Path, out_path: Path) -> list[str]:
        from app.adapters.device import has_vulkan
        cfg = self._model["config"]
        args = ["-i", str(in_path), "-o", str(out_path),
                "-m", str(self._model["model_dir"]),
                "-s", str(cfg["scale"]), "-f", "png"]
        args += self._model_flags(cfg)
        if not has_vulkan():
            logger.warning(f"no Vulkan loader; {self.family} ncnn running in CPU mode (-g -1)")
            args += ["-g", "-1"]
        return args

    def _run_cli(self, in_path: Path, out_path: Path,
                 on_progress: Optional[Callable[[float, str], None]],
                 total_frames: int, base_done: int, timeout: float) -> None:
        self.last_run_lines = []               # per-run NFR2 evidence (no stale carryover)
        state: dict = {}

        def _on_line(line: str) -> None:
            logger.debug(f"[{self.family}] {line}")
            self.last_run_lines.append(line)
            if len(self.last_run_lines) > 200:
                self.last_run_lines.pop(0)
            if on_progress is None:
                return
            result = self._progress(line, state, base_done, total_frames)
            if result is not None:
                frac, msg = result
                on_progress(1.0 + min(frac, 0.999), msg)   # inference band: [1.0, 2.0)

        sc = CliSidecar(exe=str(self._model["exe"]), on_line=_on_line)
        sc.run(self._build_args(in_path, out_path), timeout=timeout)
        if out_path.is_file() or (out_path.is_dir() and any(out_path.iterdir())):
            return
        raise SidecarError(str(self._model["exe"]), 0,
                           f"CLI exited 0 but produced no output at {out_path}")

    # ── public inference API (self-acquiring, like the torch-era wrappers) ───
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
