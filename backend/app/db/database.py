"""
SQLModel 資料庫連線管理
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
提供 SQLite 連線引擎和 session 工廠。
所有 model 透過 SQLModel 定義，init_db() 自動建表。
"""
import logging
from pathlib import Path
from typing import Generator

from sqlmodel import SQLModel, Session, create_engine

logger = logging.getLogger(__name__)

_DB_FILENAME = "mediatranx.db"
_engine = None


def _get_db_path() -> Path:
    from app.engine.paths import get_base_data_dir
    return get_base_data_dir() / _DB_FILENAME


def get_engine():
    """取得全域 SQLAlchemy Engine（lazy init）"""
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
    """取得 SQLModel Session（用於 with 語句或 FastAPI Depends）"""
    with Session(get_engine()) as session:
        yield session


def init_db() -> None:
    """建立所有 SQLModel 定義的表（CREATE IF NOT EXISTS）"""
    # 確保所有 model 都被 import（觸發 SQLModel metadata 註冊）
    import app.db.models.task_history  # noqa: F401
    import app.db.models.api_connection  # noqa: F401

    engine = get_engine()

    # 啟用 WAL 模式
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    SQLModel.metadata.create_all(engine)

    # 簡易 migration：補齊舊 DB 缺少的欄位
    _run_migrations(engine)

    logger.info("Database tables initialized")


def _run_migrations(engine):
    """補齊舊版 DB 缺少的欄位（ALTER TABLE ADD COLUMN）"""
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
