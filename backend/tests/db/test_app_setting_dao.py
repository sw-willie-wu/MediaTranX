"""AppSettingDAO tests (use the in-memory real_db fixture)."""
import pytest

from app.db.dao.app_setting_dao import AppSettingDAO


@pytest.fixture
def dao(real_db):
    return AppSettingDAO()


def test_get_missing_returns_none(dao):
    assert dao.get("nope") is None


def test_set_then_get_roundtrips_dict(dao):
    dao.set("video_download", {"enabled": True, "max_height": 1080})
    assert dao.get("video_download") == {"enabled": True, "max_height": 1080}


def test_set_is_upsert(dao):
    dao.set("video_download", {"enabled": False})
    dao.set("video_download", {"enabled": True, "quality_mode": "auto"})
    assert dao.get("video_download") == {"enabled": True, "quality_mode": "auto"}


def test_get_all_returns_decoded_map(dao):
    dao.set("a", {"x": 1})
    dao.set("b", {"y": 2})
    assert dao.get_all() == {"a": {"x": 1}, "b": {"y": 2}}


def test_get_tolerates_corrupt_json(dao):
    # Manually insert invalid JSON to prove get() degrades to {} not raises.
    from sqlmodel import Session
    from app.db.database import get_engine
    from app.db.models.app_setting import AppSetting
    with Session(get_engine()) as session:
        session.add(AppSetting(key="bad", value="{not json"))
        session.commit()
    assert dao.get("bad") == {}
