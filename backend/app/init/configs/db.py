"""Database settings."""
from pydantic import BaseModel


class DatabaseSettings(BaseModel):
    dsn: str = "sqlite:///mediatranx.db"
