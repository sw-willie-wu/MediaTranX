"""AppSetting model: table registration + defaults (uses real_db fixture)."""
import app.db.database as database
from sqlmodel import Session

from app.db.models.app_setting import AppSetting


def test_app_setting_table_roundtrips(real_db):
    with Session(database.get_engine()) as session:
        session.add(AppSetting(key="video_download", value='{"enabled": true}'))
        session.commit()
    with Session(database.get_engine()) as session:
        row = session.get(AppSetting, "video_download")
    assert row is not None
    assert row.key == "video_download"
    assert row.value == '{"enabled": true}'
    assert row.updated_at  # default_factory populated an ISO string


def test_app_setting_default_value_is_empty_object(real_db):
    with Session(database.get_engine()) as session:
        session.add(AppSetting(key="k1"))
        session.commit()
        row = session.get(AppSetting, "k1")
    assert row.value == "{}"
