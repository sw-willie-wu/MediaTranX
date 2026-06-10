"""Tests for SetupService — model download orchestration + system status."""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from app.services.setup.manager_service import SetupService


def _make_svc():
    tm = MagicMock()
    mm = MagicMock()
    svc = SetupService(task_manager=tm, model_manager=mm)
    return svc, tm, mm


class TestInit:
    def test_registers_model_download_handler(self):
        _, tm, _ = _make_svc()
        tm.register_handler.assert_called_once()
        args, kwargs = tm.register_handler.call_args
        assert args[0] == "setup.model_download"
        assert kwargs.get("output_policy") == "history"


class TestSubmitModelDownload:
    async def test_submit_returns_task_id(self):
        svc, tm, _ = _make_svc()

        async def _async(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async(*a, **k)

        tid = await svc.submit_model_download("realesrgan-x4plus")
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == "setup.model_download"
        assert args[1]["id"] == "realesrgan-x4plus"


class TestGetSystemStatus:
    async def test_returns_full_status_dict(self):
        svc, _, mm = _make_svc()
        mm.is_llama_ready.return_value = True

        with patch("app.adapters.device.get_device_info", return_value={"gpu": "yes"}), \
             patch("app.adapters.device.select_torch_index", return_value="cu128"):
            status = await svc.get_system_status()

        assert status["device"] == {"gpu": "yes"}
        assert status["llama_ready"] is True
        assert status["torch_index"] == "cu128"
        assert "base_dir" in status
        assert "python_version" in status
        assert "components" in status


class TestComponentVersions:
    """`SETTINGS.path.{ffmpeg,ytdlp,llama,soundfonts}` are computed_fields derived
    from `root` — can't monkeypatch them directly. Build a duck-typed fake
    settings namespace and pass it in."""

    def _fake_settings(self, tmp_path):
        from types import SimpleNamespace
        return SimpleNamespace(path=SimpleNamespace(
            ffmpeg=tmp_path / "ffmpeg",
            ytdlp=tmp_path / "yt-dlp",
            llama=tmp_path / "llama",
            soundfonts=tmp_path / "soundfonts",
        ))

    def test_reads_version_files_for_known_tools(self, tmp_path):
        s = self._fake_settings(tmp_path)
        s.path.ffmpeg.mkdir()
        (s.path.ffmpeg / ".version").write_text(
            '{"tag": "n7.0", "variant": "win64-gpl"}', encoding="utf-8"
        )
        s.path.ytdlp.mkdir()
        (s.path.ytdlp / ".version").write_text('{"tag": "2026.03.17"}', encoding="utf-8")
        s.path.llama.mkdir()
        s.path.soundfonts.mkdir()

        result = SetupService._get_component_versions(s)
        assert "ffmpeg" in result
        assert result["ffmpeg"]["tag"] == "n7.0"
        assert result["ytdlp"]["tag"] == "2026.03.17"

    def test_skips_tools_without_version_file(self, tmp_path):
        s = self._fake_settings(tmp_path)
        for d in (s.path.ffmpeg, s.path.llama, s.path.soundfonts):
            d.mkdir()
        result = SetupService._get_component_versions(s)
        assert "ffmpeg" not in result
        assert "llama" not in result

    def test_handles_malformed_version_json(self, tmp_path):
        s = self._fake_settings(tmp_path)
        s.path.ffmpeg.mkdir()
        (s.path.ffmpeg / ".version").write_text("not valid json {{", encoding="utf-8")
        s.path.llama.mkdir()
        s.path.soundfonts.mkdir()
        result = SetupService._get_component_versions(s)
        # Malformed version is silently swallowed
        assert "ffmpeg" not in result


class TestRemoveModel:
    def test_delegates_to_removal_module(self):
        svc, _, mm = _make_svc()
        with patch("app.services.setup.manager_service.remove_model") as mock_remove:
            svc.remove_model("realesrgan-x4plus")
        mock_remove.assert_called_once_with("realesrgan-x4plus", mm)


class TestHandleModelDownload:
    def test_delegates_to_handler_module(self):
        svc, _, _ = _make_svc()
        with patch("app.services.setup.manager_service.handle_model_download",
                   return_value={"ok": True}) as mock_handle:
            result = svc._execute_model_download(
                {"id": "x4plus"}, lambda p, m: None,
            )
        mock_handle.assert_called_once()
        assert result == {"ok": True}
