"""
Database layer.
Uses SQLModel (SQLAlchemy + Pydantic) for persistent data management.
"""
from .database import get_engine, get_session, init_db

__all__ = ["get_engine", "get_session", "init_db"]
