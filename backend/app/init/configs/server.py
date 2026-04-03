"""Server & runtime settings."""
from pydantic import BaseModel
from typing import Literal


class ServerSettings(BaseModel):
    mode: Literal["production", "dev"] = "production"
    host: str = "127.0.0.1"
    port: int = 8001
    log_level: str = "warning"
