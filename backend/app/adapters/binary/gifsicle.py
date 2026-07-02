"""Wrapper around the gifsicle binary (provided by the gifsicle-bin wheel).

gifsicle is invoked as a separate process at arm's length (GPL v2, same
posture as ffmpeg). The binary is put on PATH by gifsicle-bin's console
script; we resolve it with shutil.which and, as a packaged-build fallback,
by deriving the venv Scripts dir from gifsicle_bin.__file__.
"""
import logging
import os
import shutil
import subprocess
import sysconfig
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class GifsicleNotFound(RuntimeError):
    pass


class GifsicleError(RuntimeError):
    pass


def _resolve_gifsicle() -> Optional[str]:
    """Return the path to the gifsicle binary, or None if unresolvable.

    Resolution order (first existing file wins):
    1. shutil.which("gifsicle")          — dev / system install / PATH
    2. gifsicle_bin.__file__ derivation  — robust packaged-build fallback
       <venv>/Scripts/gifsicle.exe  (Windows)
       <venv>/bin/gifsicle           (posix)
    3. sysconfig.get_path("scripts")     — last-resort best-effort
    """
    exe_suffix: str = sysconfig.get_config_var("EXE") or ""  # ".exe" on Win, "" on posix

    # 1. PATH-based resolution (works in dev and when venv Scripts is on PATH)
    candidate = shutil.which("gifsicle")
    if candidate and os.path.isfile(candidate):
        return candidate

    # 2. Derive from gifsicle_bin.__file__ — reliable even in the frozen build
    #    because the app imports gifsicle_bin from the runtime venv's site-packages.
    #    Layout: <venv>/Lib/site-packages/gifsicle_bin/__init__.py
    #            <venv>/Scripts/gifsicle.exe  (Windows)
    #            <venv>/bin/gifsicle          (posix)
    try:
        import gifsicle_bin  # noqa: PLC0415
        pkg_init = Path(gifsicle_bin.__file__)  # …/gifsicle_bin/__init__.py
        site_packages = pkg_init.parent.parent   # …/Lib/site-packages  or  …/lib/python3.x/site-packages
        venv_root = site_packages.parent.parent  # …/  (two levels up on both Windows and posix)
        # Windows layout uses Lib\site-packages (one level deep under venv root via Scripts)
        for scripts_dir in ("Scripts", "bin"):
            binary = venv_root / scripts_dir / f"gifsicle{exe_suffix}"
            if binary.is_file():
                return str(binary)
    except Exception:  # noqa: BLE001 — missing wheel, import error, path issues
        pass

    # 3. sysconfig fallback (may point at wrong prefix under frozen core.exe, but try)
    try:
        scripts = sysconfig.get_path("scripts")
        if scripts:
            binary = os.path.join(scripts, f"gifsicle{exe_suffix}")
            if os.path.isfile(binary):
                return binary
    except Exception:  # noqa: BLE001
        pass

    return None


class GifsicleWrapper:
    def __init__(self, gifsicle_path: Optional[str] = None,
                 _resolver: Callable[[], Optional[str]] = _resolve_gifsicle):
        self._path = gifsicle_path or _resolver()
        # Construction intentionally succeeds even when gifsicle is unavailable,
        # so PNG/JPEG/WebP compress (which does NOT use gifsicle) is unaffected.
        # The error is deferred to compress() where GIF processing is attempted.

    def build_args(self, src: Path, dst: Path, *, lossy: int,
                   colors: Optional[int], frame_select: list[str],
                   optimize_transparency: bool, coalesce: bool) -> list[str]:
        args: list[str] = [self._path]  # type: ignore[list-item]
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
        if not self._path:
            raise GifsicleNotFound(
                "gifsicle binary could not be resolved (gifsicle-bin wheel installed?)"
            )
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
