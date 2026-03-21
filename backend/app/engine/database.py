"""
共用 SQLite 資料庫模組
提供 thread-local 連線管理、統一 DB 路徑與 WAL 設定。
所有需要持久化的 service 透過此模組取得連線。
"""
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_FILENAME = "mediatranx.db"


def _get_db_path() -> Path:
    from app.engine.paths import get_base_data_dir
    return get_base_data_dir() / _DB_FILENAME


class Database:
    """Thread-safe SQLite 連線管理（單例）"""

    _instance: Optional["Database"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._db_path = str(_get_db_path())
        self._local = threading.local()
        self._initialized = True
        logger.info(f"Database initialized (path={self._db_path})")

    @property
    def path(self) -> str:
        return self._db_path

    def conn(self) -> sqlite3.Connection:
        """取得當前 thread 的連線（lazy init）"""
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self._db_path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            self._local.conn = c
        return c

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        """執行 SQL 並回傳 cursor"""
        return self.conn().execute(sql, params)

    def executemany(self, sql: str, seq: list) -> sqlite3.Cursor:
        """批次執行"""
        return self.conn().executemany(sql, seq)

    def commit(self) -> None:
        self.conn().commit()

    def fetchone(self, sql: str, params: tuple | list = ()) -> Optional[sqlite3.Row]:
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def init_table(self, ddl: str) -> None:
        """執行 CREATE TABLE IF NOT EXISTS（含 commit）"""
        self.execute(ddl)
        self.commit()


_db: Optional[Database] = None


def get_database() -> Database:
    """取得全域 Database 單例"""
    global _db
    if _db is None:
        _db = Database()
    return _db
