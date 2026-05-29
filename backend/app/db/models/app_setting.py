"""Generic key-value app settings persisted in SQLite.

One row per setting namespace; `value` is a JSON-encoded blob. The first (and,
this iteration, only) consumer is the `video_download` feature flag/quality
config, which must survive restarts (unlike localStorage) and be enforced
server-side. Designed as the future extension point for migrating other
frontend-only state into the DB — but only `video_download` is wired now.
"""
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AppSetting(SQLModel, table=True):
    """A single setting row keyed by namespace string."""
    __tablename__ = "app_settings"

    key: str = Field(primary_key=True)  # namespace, e.g. "video_download"
    value: str = Field(default="{}")    # JSON-encoded dict
    updated_at: str = Field(default_factory=_now_iso)  # ISO 8601
