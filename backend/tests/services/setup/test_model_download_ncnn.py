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
        calls = _record_downloads(monkeypatch)
        mds.handle_model_download({"id": "waifu2x-cunet-art-2x"}, _noop)
        assert calls == [
            (f"{_NCNN_BASE_URL}/scale2.0x_model.param",
             models_root / "waifu2x" / "scale2.0x_model.param"),
            (f"{_NCNN_BASE_URL}/scale2.0x_model.bin",
             models_root / "waifu2x" / "scale2.0x_model.bin"),
        ]

    def test_real_cugan_longest_prefix_routing(self, models_root, monkeypatch):
        # multi-hyphen family must resolve to `real-cugan`, not `real`.
        calls = _record_downloads(monkeypatch)
        mds.handle_model_download({"id": "real-cugan-up2x-conservative"}, _noop)
        assert calls == [
            (f"{_NCNN_BASE_URL}/up2x-conservative.param",
             models_root / "real-cugan" / "up2x-conservative.param"),
            (f"{_NCNN_BASE_URL}/up2x-conservative.bin",
             models_root / "real-cugan" / "up2x-conservative.bin"),
        ]

    def test_skips_existing_file(self, models_root, monkeypatch):
        slot = models_root / "waifu2x"
        slot.mkdir(parents=True)
        (slot / "scale2.0x_model.param").write_bytes(b"x")   # already present
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
    def test_removes_both_files_waifu2x(self, models_root):
        slot = models_root / "waifu2x"
        slot.mkdir(parents=True)
        for f in ("scale2.0x_model.param", "scale2.0x_model.bin"):
            (slot / f).write_bytes(b"x")
        mrs.remove_model("waifu2x-cunet-art-2x", MagicMock())
        assert not (slot / "scale2.0x_model.param").exists()
        assert not (slot / "scale2.0x_model.bin").exists()

    def test_removes_both_files_real_cugan_longest_prefix(self, models_root):
        slot = models_root / "real-cugan"
        slot.mkdir(parents=True)
        for f in ("up2x-conservative.param", "up2x-conservative.bin"):
            (slot / f).write_bytes(b"x")
        mrs.remove_model("real-cugan-up2x-conservative", MagicMock())
        assert not (slot / "up2x-conservative.param").exists()
        assert not (slot / "up2x-conservative.bin").exists()
