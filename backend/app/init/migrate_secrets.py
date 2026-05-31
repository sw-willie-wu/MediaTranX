"""One-time data migration: encrypt legacy plaintext api_keys at rest.

Operates on the RAW column via a dedicated session (does NOT go through any
decrypt-on-read path). Idempotent (skips already enc:-marked rows). Per-row
commit. Never overwrites a row it can't handle. Runs in lifespan startup after
init_db(). Distinct from database._run_migrations (schema) — this is data."""
from __future__ import annotations
import logging
from sqlmodel import Session, select
import app.db.database as database          # qualified call so test fixtures that
from app.db.models.api_connection import ApiConnection  # patch database.get_engine reach us (review I2)
from app.adapters.security.secret_cipher import get_secret_cipher

logger = logging.getLogger(__name__)


def migrate_plaintext_keys() -> None:
    cipher = get_secret_cipher()
    engine = database.get_engine()
    with Session(engine) as session:
        rows = session.exec(select(ApiConnection)).all()
        for conn in rows:
            key = conn.api_key
            if not key or key.startswith("enc:"):
                continue                          # empty or already encrypted
            try:
                conn.api_key = cipher.encrypt(key)
                session.add(conn)
                session.commit()                  # per-row
            except Exception as e:                # noqa: BLE001
                session.rollback()
                logger.warning("secret migration skipped conn %s: %s", conn.id, e)
