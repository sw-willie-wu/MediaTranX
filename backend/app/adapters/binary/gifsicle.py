"""Wrapper around the gifsicle binary (provided by the gifsicle-bin wheel).

gifsicle is invoked as a separate process at arm's length (GPL v2, same
posture as ffmpeg). The binary is put on PATH by gifsicle-bin's console
script; we resolve it with shutil.which.
"""
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class GifsicleNotFound(RuntimeError):
    pass


class GifsicleError(RuntimeError):
    pass


class GifsicleWrapper:
    def __init__(self, gifsicle_path: Optional[str] = None,
                 _which: Callable[[str], Optional[str]] = shutil.which):
        self._path = gifsicle_path or _which("gifsicle")
        if not self._path:
            raise GifsicleNotFound(
                "gifsicle not found on PATH; is the gifsicle-bin wheel installed?"
            )

    def build_args(self, src: Path, dst: Path, *, lossy: int,
                   colors: Optional[int], frame_select: list[str],
                   optimize_transparency: bool, coalesce: bool) -> list[str]:
        args: list[str] = [self._path]
        if coalesce:
            args.append("--unoptimize")
            args.append(str(src))
        else:
            args.append("-O3" if optimize_transparency else "-O2")
            if lossy > 0:
                args.append(f"--lossy={lossy}")
            if colors:
                args.append(f"--colors={colors}")
            args.append(str(src))
            args += frame_select
        args += ["-o", str(dst)]
        return args

    def compress(self, src: Path, dst: Path, *, lossy: int = 0,
                 colors: Optional[int] = None, frame_drop: int = 0,
                 optimize_transparency: bool = True, coalesce: bool = False) -> None:
        frame_select: list[str] = []
        if frame_drop and frame_drop > 1 and not coalesce:
            from PIL import Image
            with Image.open(src) as im:
                n = getattr(im, "n_frames", 1)
            kept = [i for i in range(n) if (i + 1) % frame_drop != 0]
            frame_select = [f"#{i}" for i in kept]
        args = self.build_args(src, dst, lossy=lossy, colors=colors,
                               frame_select=frame_select,
                               optimize_transparency=optimize_transparency,
                               coalesce=coalesce)
        logger.info("gifsicle: %s", " ".join(args))
        proc = subprocess.run(args, capture_output=True, text=True)
        if proc.returncode != 0:
            raise GifsicleError(f"gifsicle exit {proc.returncode}: {proc.stderr.strip()}")
