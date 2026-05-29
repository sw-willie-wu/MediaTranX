"""
SQLModel database connection management.
Provides SQLite connection engine and session factory.
All models are defined via SQLModel; init_db() auto-creates tables.
"""
import logging
from pathlib import Path
from typing import Generator

from sqlmodel import SQLModel, Session, create_engine

logger = logging.getLogger(__name__)

_DB_FILENAME = "mediatranx.db"
_engine = None


def _get_db_path() -> Path:
    from app.init.configs import SETTINGS
    return SETTINGS.path.root / _DB_FILENAME


def get_engine():
    """Get the global SQLAlchemy Engine (lazy init)."""
    global _engine
    if _engine is None:
        db_path = _get_db_path()
        db_url = f"sqlite:///{db_path}"
        _engine = create_engine(
            db_url,
            echo=False,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
        )
        logger.info(f"Database engine created (path={db_path})")
    return _engine


def get_session() -> Generator[Session, None, None]:
    """Get a SQLModel Session (for use with 'with' statement or FastAPI Depends)."""
    with Session(get_engine()) as session:
        yield session


def init_db() -> None:
    """Create all SQLModel-defined tables (CREATE IF NOT EXISTS)."""
    # Ensure all models are imported (triggers SQLModel metadata registration)
    import app.db.models.task_history  # noqa: F401
    import app.db.models.api_connection  # noqa: F401
    import app.db.models.agent_session  # noqa: F401
    import app.db.models.agent_message  # noqa: F401

    engine = get_engine()

    # Enable WAL mode
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    SQLModel.metadata.create_all(engine)

    # Simple migration: add missing columns in older DBs
    _run_migrations(engine)

    logger.info("Database tables initialized")


def _run_migrations(engine):
    """Add missing columns in older DB versions (ALTER TABLE ADD COLUMN)."""
    from sqlalchemy import text, inspect as sa_inspect
    inspector = sa_inspect(engine)

    migrations = [
        ("task_history", "error_code", "TEXT"),
    ]

    with engine.connect() as conn:
        for table, column, col_type in migrations:
            if table not in inspector.get_table_names():
                continue
            existing = [c["name"] for c in inspector.get_columns(table)]
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                logger.info(f"Migration: added {table}.{column}")
        conn.commit()
