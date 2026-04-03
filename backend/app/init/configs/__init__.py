"""
Application settings -- single source of truth for all configuration.
Replaces engine/paths.py, config.json, and scattered env vars.
"""
import os
import sys
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .server import ServerSettings
from .paths import PathSettings
from .db import DatabaseSettings


class AppSettings(BaseSettings):
    # Platform detection (set at startup, immutable)
    is_frozen: bool = False
    platform: str = ""

    # Nested settings
    server: ServerSettings = ServerSettings()
    path: PathSettings = PathSettings()
    db: DatabaseSettings = DatabaseSettings()

    model_config = SettingsConfigDict(
        env_prefix="MEDIATRANX_",
        env_file=None,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    @model_validator(mode="after")
    def _resolve_defaults(self) -> "AppSettings":
        """Fill empty paths with platform-aware defaults."""
        if not self.platform:
            self.platform = sys.platform

        # data dir
        if not self.path.data:
            if self.is_frozen:
                if self.platform == "win32":
                    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
                else:
                    appdata = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
                self.path.data = str(Path(appdata) / "MediaTranX")
            else:
                # Dev mode: core/backend/
                # __file__ = backend/app/init/configs/__init__.py -> go up 4 levels
                self.path.data = str(Path(__file__).resolve().parent.parent.parent.parent)

        base = Path(self.path.data)

        if not self.path.models:
            self.path.models = str(base / "models")
        if not self.path.temp:
            self.path.temp = str(base / "temp")
        if not self.path.venv:
            self.path.venv = str(base / ".venv")

        if not self.path.ffmpeg:
            self.path.ffmpeg = str(base / "bin" / "ffmpeg")
        if not self.path.fluidsynth:
            self.path.fluidsynth = str(base / "bin" / "fluidsynth")
        if not self.path.llama_bin:
            if self.is_frozen:
                self.path.llama_bin = str(base / "llama-bin")
            else:
                self.path.llama_bin = str(base / "bin" / "llama")

        if not self.db.dsn:
            self.db.dsn = f"sqlite:///{base / 'mediatranx.db'}"

        # Auto log level
        if self.server.mode == "dev" and self.server.log_level == "warning":
            self.server.log_level = "debug"

        return self


# Global singleton -- initialized in main.py, read everywhere
_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """Get the global AppSettings instance. Must be initialized first."""
    if _settings is None:
        raise RuntimeError("AppSettings not initialized. Call init_settings() first.")
    return _settings


def _resolve_env_path(is_frozen: bool, platform: str) -> Path | None:
    """Compute .env file path based on runtime mode. Called before AppSettings init."""
    if is_frozen:
        if platform == "win32":
            appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        else:
            appdata = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        data = Path(appdata) / "MediaTranX"
    else:
        # __file__ = backend/app/init/configs/__init__.py -> up 4 levels = backend/
        data = Path(__file__).resolve().parent.parent.parent.parent
    env = data / ".env"
    return env if env.exists() else None


def init_settings(**overrides) -> AppSettings:
    """Initialize the global AppSettings. Called once at startup."""
    global _settings
    env_path = _resolve_env_path(
        overrides.get("is_frozen", False),
        overrides.get("platform", sys.platform),
    )
    _settings = AppSettings(_env_file=env_path, **overrides)
    return _settings
