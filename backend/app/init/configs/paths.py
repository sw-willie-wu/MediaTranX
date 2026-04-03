"""Path resolution settings."""
from pydantic import BaseModel


class PathSettings(BaseModel):
    data: str = ""
    models: str = ""
    temp: str = ""
    ffmpeg: str = ""
    fluidsynth: str = ""
    llama_bin: str = ""
    venv: str = ""
