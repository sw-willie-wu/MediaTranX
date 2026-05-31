"""DAO for the generic key-value AppSetting store."""
import json
import logging
from typing import Optional

from sqlmodel import Session, select

from app.db.database import get_engine
from app.db.models.app_setting import AppSetting, _now_iso

logger = logging.getLogger(__name__)


class AppSettingDAO:
    """Get/set JSON-blob settings keyed by namespace string."""

    def get(self, key: str) -> Optional[dict]:
        """Return the decoded dict for *key*, or None if the key is absent.

        Corrupt JSON degrades to {} (logged) rather than raising — callers
        treat 'present but unreadable' the same as 'empty config'.
        """
        with Session(get_engine()) as session:
            row = session.get(AppSetting, key)
        if row is None:
            return None
        try:
            return json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            logger.warning("AppSetting %r has invalid JSON; treating as empty", key)
            return {}

    def set(self, key: str, value: dict) -> None:
        """Upsert *value* (a JSON-serialisable dict) under *key*."""
        encoded = json.dumps(value)
        with Session(get_engine()) as session:
            row = session.get(AppSetting, key)
            if row is None:
                session.add(AppSetting(key=key, value=encoded, updated_at=_now_iso()))
            else:
                row.value = encoded
                row.updated_at = _now_iso()
            session.commit()

    def get_all(self) -> dict[str, dict]:
        """Return every setting as {key: decoded_dict} (corrupt rows → {})."""
        with Session(get_engine()) as session:
            rows = session.exec(select(AppSetting)).all()
        out: dict[str, dict] = {}
        for row in rows:
            try:
                out[row.key] = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                out[row.key] = {}
        return out
