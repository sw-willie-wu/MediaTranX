"""
Application settings -- single source of truth for all configuration.
"""
import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .server import ServerSettings
from .paths import PathSettings
from .db import DatabaseSettings


def _find_env_file() -> str | None:
    """Locate .env file: use MEDIATRANX_PATH__ROOT if set, otherwise cwd."""
    root_dir = os.environ.get('MEDIATRANX_PATH__ROOT')
    if root_dir:
        env = Path(root_dir) / '.env'
        return str(env) if env.exists() else None
    env = Path('.env')
    return str(env) if env.exists() else None


class AppSettings(BaseSettings):
    is_frozen: bool = False
    platform: str = sys.platform

    server: ServerSettings = ServerSettings()
    path: PathSettings = PathSettings()
    db: DatabaseSettings = DatabaseSettings()

    model_config = SettingsConfigDict(
        env_prefix="MEDIATRANX_",
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )


SETTINGS = AppSettings()
