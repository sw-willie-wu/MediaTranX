from pathlib import Path
from typing import Literal
from configparser import ConfigParser

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class UISettings(BaseModel):
    
    StaticFiles: Path = Field(
        default=Path(__file__).parent.parent / 'static',
        description='前端靜態檔編譯後路徑'
    )
    ThemeMode: Literal['LIGHT', 'DARK', 'AUTO'] = Field(
        default='AUTO',
        description='主題配色'
    )

class Settings(BaseSettings):
    Mode: Literal['DEV', 'PROD'] = Field(
        default='PROD'
    )
    UI: UISettings = UISettings()


settings = Settings()