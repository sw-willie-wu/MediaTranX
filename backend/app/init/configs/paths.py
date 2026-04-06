"""Path resolution settings."""
import sys
from pathlib import Path
from pydantic import BaseModel, model_validator

_WIN = sys.platform == "win32"


class PathSettings(BaseModel):
    """Path configuration. Defaults are relative to cwd (core/backend/ in dev).
    In production, Electron overrides via MEDIATRANX_PATH__* env vars."""
    data: Path = Path(".")
    venv: Path = Path(".venv")
    bin: Path = Path("bin")
    models: Path = Path("models")
    temp: Path = Path("data/temp")

    # Windows: derived from bin. Linux/macOS: system binary name.
    ffmpeg: Path = Path("bin/ffmpeg") if _WIN else Path("ffmpeg")
    fluidsynth: Path = Path("bin/fluidsynth") if _WIN else Path("fluidsynth")
    llama: Path = Path("bin/llama")

    @model_validator(mode="after")
    def _derive_bin_paths(self) -> "PathSettings":
        """When bin is overridden (e.g. by Electron), update tool paths to match."""
        if self.bin != Path("bin"):
            b = self.bin
            if _WIN and self.ffmpeg == Path("bin/ffmpeg"):
                self.ffmpeg = b / "ffmpeg"
            if _WIN and self.fluidsynth == Path("bin/fluidsynth"):
                self.fluidsynth = b / "fluidsynth"
            if self.llama == Path("bin/llama"):
                self.llama = b / "llama"
        return self
