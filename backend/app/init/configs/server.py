"""Server & runtime settings."""
from pydantic import BaseModel, model_validator
from typing import Literal


class ServerSettings(BaseModel):
    mode: Literal["production", "dev"] = "production"
    host: str = "127.0.0.1"
    port: int = 8001
    log_level: str = "warning"

    @model_validator(mode="after")
    def _auto_log_level(self) -> "ServerSettings":
        if self.mode == "dev" and self.log_level == "warning":
            self.log_level = "debug"
        return self
