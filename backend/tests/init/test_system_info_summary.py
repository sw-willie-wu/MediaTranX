"""collect_env_summary / app_version 純函式測試。"""
from unittest.mock import patch

from app.init import system_info


def test_app_version_prefers_env(monkeypatch):
    monkeypatch.setenv("MEDIATRANX_APP_VERSION", "9.9.9")
    assert system_info.app_version() == "9.9.9"


def test_app_version_fallback_unknown(monkeypatch):
    monkeypatch.delenv("MEDIATRANX_APP_VERSION", raising=False)
    with patch("app.init.system_info.metadata.version", side_effect=Exception("no pkg")):
        assert system_info.app_version() == "unknown"


def test_collect_env_summary_contains_core_fields(settings):
    text = system_info.collect_env_summary(settings)
    assert "OS:" in text
    assert "Python:" in text


def test_collect_env_summary_never_raises(settings):
    # 底層 device info 爆炸也不能 raise（保留既有逐欄位 guard 性質）
    with patch("app.init.system_info._collect_device_lines", side_effect=Exception("boom")):
        text = system_info.collect_env_summary(settings)
        assert isinstance(text, str)
