from sqlalchemy import create_engine, text, inspect
from app.db.database import _run_migrations


def test_migration_adds_chunk_ctx_budget(tmp_path):
    db = tmp_path / "old.db"
    eng = create_engine(f"sqlite:///{db}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE api_connections "
                       "(id INTEGER PRIMARY KEY, provider TEXT, name TEXT, "
                       "endpoint TEXT, api_key TEXT, enabled BOOLEAN, "
                       "created_at TEXT, updated_at TEXT)"))
        c.commit()
    _run_migrations(eng)
    cols = [c["name"] for c in inspect(eng).get_columns("api_connections")]
    assert "chunk_ctx_budget" in cols


def test_migration_idempotent(tmp_path):
    db = tmp_path / "x.db"
    eng = create_engine(f"sqlite:///{db}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE api_connections (id INTEGER PRIMARY KEY, "
                       "chunk_ctx_budget INTEGER)"))
        c.commit()
    _run_migrations(eng)  # must not raise on existing column
    _run_migrations(eng)
