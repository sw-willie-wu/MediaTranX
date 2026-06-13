"""SR model wrappers (RealESRGANWrapper / Waifu2xWrapper): slot, per-model CLI
knowledge (_model_flags / _progress), file validation, and the enhance path that
delegates to the NcnnVulkan binary adapter.

The execution mechanics (arg skeleton, output check, progress band) are tested in
tests/adapters/test_ncnn_binary.py — here we only cover the model-specific bits.
Seam: patch `app.adapters.binary.ncnn.CliSidecar` + each wrapper's `_ncnn.exe_path`.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.adapters.binary import ncnn as ncnn_mod
from app.adapters.ai.wrapper.realesrgan import RealESRGANWrapper
from app.adapters.ai.wrapper.waifu2x import Waifu2xWrapper
from app.adapters.binary.sidecar import SidecarError


def _fake_sidecar(lines=(), out_files=1):
    class _FakeSC:
        def __init__(self, exe, on_line=None, cwd=None):
            self.on_line = on_line

        def run(self, args, timeout=None):
            for ln in lines:
                if self.on_line:
                    self.on_line(ln)
            out = Path(args[args.index("-o") + 1])
            if out.suffix == ".png":
                out.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (128, 128)).save(out, "PNG")
            else:
                out.mkdir(parents=True, exist_ok=True)
                for i in range(out_files):
                    Image.new("RGB", (8, 8)).save(out / f"f{i}.png", "PNG")
            return 0
    return _FakeSC


def _fake_acquire(w, model):
    @contextmanager
    def _acq(model_id=None, variant=None, on_progress=None):
        w._model = model
        yield w
    return _acq


def _model(tmp_path, files=("a.param", "a.bin"), **cfg_extra):
    md = tmp_path; cfg = {"scale": 4, "variant": "v", "files": list(files), **cfg_extra}
    return {"model_dir": md, "config": cfg}


# -- slot -----------------------------------------------------------------

@pytest.mark.parametrize("cls", [RealESRGANWrapper, Waifu2xWrapper])
def test_slot_is_upscale(cls):
    assert cls().slot == "upscale"


# -- per-model CLI flags --------------------------------------------------

def test_realesrgan_flags_use_model_name_no_verbose():
    assert RealESRGANWrapper()._model_flags({"cli_model_name": "realesrgan-x4plus"}) \
        == ["-n", "realesrgan-x4plus"]


def test_waifu2x_flags_use_noise_and_verbose():
    assert Waifu2xWrapper()._model_flags({"cli_noise": -1}) == ["-n", "-1", "-v"]


# -- per-model progress parsing -------------------------------------------
# Real CLI behaviour (T8, 2026-06-12): realesrgan prints one "0.00%" per frame
# and climbs to "97.96%", NEVER "100.00%"; waifu2x prints a "done" line per file.

def test_realesrgan_progress_advances_without_ever_seeing_100pct():
    w = RealESRGANWrapper(); state = {}
    fracs = [w._progress(l, state, 0, 2)[0]
             for l in ("0.00%", "97.96%", "0.00%", "97.96%")]
    assert fracs == sorted(fracs)          # monotonic
    assert fracs[-1] > 0.9                 # 2nd frame counted, not frozen at ~0.49
    assert w._progress("not a percent", state, 0, 2) is None


def test_waifu2x_progress_counts_done_lines():
    w = Waifu2xWrapper(); state = {}
    f1, m1 = w._progress("a -> b done", state, 0, 2)
    f2, _ = w._progress("c -> d done", state, 0, 2)
    assert f1 == pytest.approx(0.5) and "upscale_frame|1|2" in m1
    assert f2 == pytest.approx(1.0)
    assert w._progress("no progress here", state, 0, 2) is None


# -- _load_impl file validation -------------------------------------------

def test_load_fails_listing_missing_model_files(tmp_path):
    w = RealESRGANWrapper()
    param = tmp_path / "realesrgan" / "realesrgan-x4plus.param"
    param.parent.mkdir(parents=True)
    param.write_bytes(b"x")   # .param present, .bin absent
    cfg = {"variant": "x4plus", "slot": "realesrgan",
           "files": ["realesrgan-x4plus.param", "realesrgan-x4plus.bin"]}
    with pytest.raises(FileNotFoundError, match="missing"):
        w._load_impl(param, cfg)


def test_load_impl_none_path_names_expected_location():
    with pytest.raises(FileNotFoundError, match="(?i)waifu2x"):
        Waifu2xWrapper()._load_impl(None, {"variant": "cunet-art-2x", "slot": "waifu2x"})


# -- enhance delegates to NcnnVulkan --------------------------------------

def test_enhance_round_trips_through_binary_adapter(tmp_path, monkeypatch):
    w = RealESRGANWrapper()
    monkeypatch.setattr(w._ncnn, "exe_path", lambda: "exe")
    monkeypatch.setattr(ncnn_mod, "CliSidecar", _fake_sidecar())
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    model = _model(tmp_path, cli_model_name="realesrgan-x4plus")
    with patch.object(w, "acquire", _fake_acquire(w, model)):
        out = w.enhance(Image.new("RGB", (64, 64)), model_id="x4plus")
    assert isinstance(out, Image.Image) and out.size == (128, 128)


def test_last_run_lines_proxies_the_binary_adapter(tmp_path, monkeypatch):
    w = Waifu2xWrapper()
    monkeypatch.setattr(w._ncnn, "exe_path", lambda: "exe")
    monkeypatch.setattr(ncnn_mod, "CliSidecar", _fake_sidecar(lines=["[0 FakeGPU]"]))
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    model = _model(tmp_path, cli_noise=-1)
    with patch.object(w, "acquire", _fake_acquire(w, model)):
        w.enhance(Image.new("RGB", (8, 8)), model_id="cunet-art-2x")
    assert any("[0 FakeGPU]" in line for line in w.last_run_lines)
