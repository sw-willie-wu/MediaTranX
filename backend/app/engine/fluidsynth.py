"""
FluidSynth CLI wrapper — SoundFont-based MIDI rendering via subprocess.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from app.init.configs import SETTINGS

logger = logging.getLogger(__name__)

SF2_FILENAME = "FluidR3_GM.sf2"
EXE_FILENAME = "fluidsynth.exe" if sys.platform == "win32" else "fluidsynth"


class FluidSynthWrapper:
    """SoundFont loading and MIDI→WAV rendering via fluidsynth CLI."""

    def __init__(self):
        self._dir = SETTINGS.path.fluidsynth

    @property
    def sf2_path(self) -> Path:
        return self._dir / SF2_FILENAME

    @property
    def exe_path(self) -> Path:
        return self._dir / EXE_FILENAME

    def _find_exe(self) -> str:
        """Find fluidsynth executable: bundled first, then system PATH."""
        if self.exe_path.exists():
            return str(self.exe_path)
        system_path = shutil.which("fluidsynth")
        if system_path:
            return system_path
        raise FileNotFoundError(
            f"FluidSynth not found. Expected at {self.exe_path} or in system PATH. "
            "Please download via Settings → Model Management."
        )

    def is_available(self) -> dict:
        """Check availability of FluidSynth executable and SoundFont."""
        if sys.platform == "win32":
            exe_ok = self.exe_path.exists()
        else:
            exe_ok = self.exe_path.exists() or shutil.which("fluidsynth") is not None
        sf2_ok = self.sf2_path.exists()
        return {
            "exe_available": exe_ok,
            "sf2_available": sf2_ok,
            "ready": exe_ok and sf2_ok,
        }

    def render_midi_to_wav(
        self,
        midi_path: str | Path,
        output_path: str | Path,
        sample_rate: int = 44100,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        """Render a .mid file to .wav using fluidsynth CLI."""
        status = self.is_available()
        if not status["ready"]:
            missing = []
            if not status["exe_available"]:
                missing.append("fluidsynth executable")
            if not status["sf2_available"]:
                missing.append(f"SoundFont ({SF2_FILENAME})")
            raise FileNotFoundError(
                f"FluidSynth not ready. Missing: {', '.join(missing)}. "
                "Please download via Settings → Model Management."
            )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if on_progress:
            on_progress(0.1, "Rendering MIDI...")

        exe = self._find_exe()
        cmd = [
            exe,
            "-ni",                          # non-interactive, no shell
            str(self.sf2_path),             # SoundFont
            str(midi_path),                 # input MIDI
            "-F", str(out),                 # output WAV
            "-r", str(sample_rate),         # sample rate
        ]

        logger.info(f"FluidSynth render: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"FluidSynth render failed (code {result.returncode}): {stderr}")

        if not out.exists():
            raise RuntimeError(f"FluidSynth output file not created: {out}")

        if on_progress:
            on_progress(1.0, "Rendering complete")

        logger.info(f"MIDI rendered to WAV: {out}")
        return out
