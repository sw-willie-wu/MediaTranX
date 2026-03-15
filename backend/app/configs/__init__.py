from typing import Literal
from configparser import ConfigParser

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class UISettings(BaseModel):

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