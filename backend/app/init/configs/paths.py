"""Path resolution settings."""
import sys
from pathlib import Path
from pydantic import BaseModel, computed_field

_WIN = sys.platform == "win32"


class PathSettings(BaseModel):
    """Path configuration. Defaults are relative to cwd (core/backend/ in dev).
    In production, Electron overrides via MEDIATRANX_PATH__* env vars.

    Top-level (env-overridable, user-relocatable):
      - `root`   : writable user-data root (DB, .env, manager base_dir,
                   parent of bin/.venv/logs)
      - `models` : AI models (user may move to bigger drive via Settings UI)
      - `temp`   : uploads/results/sidecars (user may move via Settings UI)

    Computed from `root`:
      - `venv`       : python virtual env (root/.venv)
      - `log`        : log files (root/logs)
      - `ffmpeg`     : Windows root/bin/ffmpeg/; Linux/macOS = system 'ffmpeg'
      - `llama`      : root/bin/llama/
      - `ytdlp`      : Windows root/bin/yt-dlp/; Linux/macOS = system 'yt-dlp'
      - `soundfonts` : root/bin/soundfonts/musyngkite/
    """
    root: Path = Path(".")
    models: Path = Path("models")
    temp: Path = Path("temp")

    @computed_field
    @property
    def venv(self) -> Path:
        return self.root / ".venv"

    @computed_field
    @property
    def log(self) -> Path:
        return self.root / "logs"

    @computed_field
    @property
    def ffmpeg(self) -> Path:
        # On non-Windows, prefer system-installed ffmpeg (binary on PATH)
        return self.root / "bin" / "ffmpeg" if _WIN else Path("ffmpeg")

    @computed_field
    @property
    def llama(self) -> Path:
        return self.root / "bin" / "llama"

    @computed_field
    @property
    def ytdlp(self) -> Path:
        # Windows: bundled in root/bin/yt-dlp/; else prefer system yt-dlp (PATH).
        return self.root / "bin" / "yt-dlp" if _WIN else Path("yt-dlp")

    @computed_field
    @property
    def soundfonts(self) -> Path:
        return self.root / "bin" / "soundfonts" / "musyngkite"
