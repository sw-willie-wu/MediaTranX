"""FORMAT_NCNN download + removal routing (re-hosted .param/.bin pairs).

Mirrors test_soundfont_download.py's style (both services exercised here).
"""
from unittest.mock import MagicMock

import pytest

from app.services.setup import model_download_service as mds
from app.services.setup import model_removal_service as mrs
from app.adapters.ai.registry import _NCNN_BASE_URL
from app.init.configs import SETTINGS


def _noop(*a, **k):
    pass


@pytest.fixture
def models_root(tmp_path, monkeypatch):
    monkeypatch.setattr(SETTINGS.path, "models", tmp_path)
    return tmp_path


def _record_downloads(monkeypatch):
    """Replace the network downloader with a recorder that also writes the file
    (so the skip-if-exists branch sees real files) and reports end progress."""
    calls = []

    def fake(url, target_path, progress_callback, base_progress=0.1, end_progress=0.95):
        progress_callback(end_progress, "x")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"x")
        calls.append((url, target_path))

    monkeypatch.setattr(mds, "_download_from_url", fake)
    return calls


class TestNcnnDownloadRouting:
    def test_waifu2x_exact_urls_and_targets(self, models_root, monkeypatch):
        # waifu2x nests under cli_model_subdir `models-cunet` (the exe infers the
        # arch from the -m dir basename); the download URL stays flat.
        calls = _record_downloads(monkeypatch)
        mds.handle_model_download({"id": "waifu2x-cunet-art-2x"}, _noop)
        assert calls == [
            (f"{_NCNN_BASE_URL}/scale2.0x_model.param",
             models_root / "waifu2x" / "models-cunet" / "scale2.0x_model.param"),
            (f"{_NCNN_BASE_URL}/scale2.0x_model.bin",
             models_root / "waifu2x" / "models-cunet" / "scale2.0x_model.bin"),
        ]

    def test_multi_hyphen_variant_id_routing(self, models_root, monkeypatch):
        # a multi-hyphen id must decompose to family `realesrgan`, variant
        # `x4plus-anime` (longest-prefix family match, then the rest is the variant).
        calls = _record_downloads(monkeypatch)
        mds.handle_model_download({"id": "realesrgan-x4plus-anime"}, _noop)
        assert calls == [
            (f"{_NCNN_BASE_URL}/realesrgan-x4plus-anime.param",
             models_root / "realesrgan" / "realesrgan-x4plus-anime.param"),
            (f"{_NCNN_BASE_URL}/realesrgan-x4plus-anime.bin",
             models_root / "realesrgan" / "realesrgan-x4plus-anime.bin"),
        ]

    def test_skips_existing_file(self, models_root, monkeypatch):
        mc = models_root / "waifu2x" / "models-cunet"
        mc.mkdir(parents=True)
        (mc / "scale2.0x_model.param").write_bytes(b"x")   # already present
        calls = _record_downloads(monkeypatch)
        mds.handle_model_download({"id": "waifu2x-cunet-art-2x"}, _noop)
        assert [c[1].name for c in calls] == ["scale2.0x_model.bin"]

    def test_progress_monotonic(self, models_root, monkeypatch):
        _record_downloads(monkeypatch)
        seen = []
        mds.handle_model_download({"id": "waifu2x-cunet-art-2x"},
                                  lambda p, m: seen.append(p))
        assert seen == sorted(seen), seen
        assert all(0.0 <= p <= 1.0 for p in seen)


class TestNcnnRemoval:
    def test_removes_both_files_waifu2x_and_prunes_subdir(self, models_root):
        slot = models_root / "waifu2x"
        mc = slot / "models-cunet"
        mc.mkdir(parents=True)
        for f in ("scale2.0x_model.param", "scale2.0x_model.bin"):
            (mc / f).write_bytes(b"x")
        mrs.remove_model("waifu2x-cunet-art-2x", MagicMock())
        assert not (mc / "scale2.0x_model.param").exists()
        assert not (mc / "scale2.0x_model.bin").exists()
        assert not mc.exists()      # empty cli_model_subdir pruned
        assert not slot.exists()    # empty slot dir pruned too

    def test_removes_both_files_multi_hyphen_variant(self, models_root):
        slot = models_root / "realesrgan"
        slot.mkdir(parents=True)
        for f in ("realesrgan-x4plus-anime.param", "realesrgan-x4plus-anime.bin"):
            (slot / f).write_bytes(b"x")
        mrs.remove_model("realesrgan-x4plus-anime", MagicMock())
        assert not (slot / "realesrgan-x4plus-anime.param").exists()
        assert not (slot / "realesrgan-x4plus-anime.bin").exists()
