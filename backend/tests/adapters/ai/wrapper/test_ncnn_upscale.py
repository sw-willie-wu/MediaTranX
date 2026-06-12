"""NcnnUpscaleWrapper: slot/family, CLI assembly, CPU fallback, progress
accumulation (count completions, not dips), output checks, NFR2 device lines.

Seams: patch `ncnn_upscale.CliSidecar` (the binary), `ncnn_upscale._exe_path`
(the installed exe), and the SOURCE `app.adapters.device.has_vulkan` (imported
lazily inside `_build_args`). Acquire is faked the way test_pth_upscaler_wrappers
fakes the manager.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.adapters.ai.wrapper import ncnn_upscale
from app.adapters.ai.wrapper.ncnn_upscale import NcnnUpscaleWrapper
from app.adapters.binary.sidecar_base import SidecarError


def _model_dict(tmp_path, *, exe_tool, scale, cli_model_name=None, cli_noise=None):
    """The dict _load_impl returns / _run_cli + _build_args read from self._model."""
    cfg = {
        "exe_tool": exe_tool, "scale": scale, "slot": exe_tool,
        "model_id": exe_tool, "variant": "v",
        "files": ["a.param", "a.bin"],
    }
    if cli_model_name is not None:
        cfg["cli_model_name"] = cli_model_name
    if cli_noise is not None:
        cfg["cli_noise"] = cli_noise
    md = tmp_path / exe_tool
    md.mkdir(parents=True, exist_ok=True)
    return {"exe": str(tmp_path / "exe"), "model_dir": md, "config": cfg}


def _fake_sidecar(lines=(), out_files=1):
    """Factory for a CliSidecar stand-in: emits `lines` then writes `out_files`
    PNG(s) at the `-o` path (a file if out_files==1 and the path looks like a
    file, else into the dir)."""
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


# -- slot / family --------------------------------------------------------

def test_slot_is_upscale_and_family_recorded():
    w = NcnnUpscaleWrapper("real-cugan")
    assert w.slot == "upscale"
    assert w.family == "real-cugan"


# -- _load_impl -----------------------------------------------------------

def test_load_fails_listing_missing_model_files(tmp_path):
    w = NcnnUpscaleWrapper("realesrgan")
    param = tmp_path / "realesrgan" / "realesrgan-x4plus.param"
    param.parent.mkdir(parents=True)
    param.write_bytes(b"x")   # .param present, .bin absent
    cfg = {"exe_tool": "realesrgan", "variant": "x4plus", "slot": "realesrgan",
           "files": ["realesrgan-x4plus.param", "realesrgan-x4plus.bin"]}
    with pytest.raises(FileNotFoundError, match="missing"):
        w._load_impl(param, cfg)


def test_load_impl_none_path_names_expected_location():
    w = NcnnUpscaleWrapper("realesrgan")
    with pytest.raises(FileNotFoundError, match="(?i)realesrgan"):
        w._load_impl(None, {"variant": "x4plus", "slot": "realesrgan"})


# -- _build_args ----------------------------------------------------------

def test_build_args_realesrgan_model_name_no_verbose(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    w = NcnnUpscaleWrapper("realesrgan")
    w._model = _model_dict(tmp_path, exe_tool="realesrgan", scale=4,
                           cli_model_name="realesrgan-x4plus")
    args = w._build_args(Path("in.png"), Path("out.png"))
    assert args == ["-i", "in.png", "-o", "out.png",
                    "-m", str(w._model["model_dir"]), "-s", "4", "-f", "png",
                    "-n", "realesrgan-x4plus"]
    assert "-v" not in args
    assert "-g" not in args            # vulkan present → no CPU flag


def test_build_args_waifu2x_noise_verbose(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    w = NcnnUpscaleWrapper("waifu2x")
    w._model = _model_dict(tmp_path, exe_tool="waifu2x", scale=2, cli_noise=-1)
    args = w._build_args(Path("in.png"), Path("out.png"))
    assert args[-3:] == ["-n", "-1", "-v"]
    assert "cli_model_name" not in w._model["config"]


def test_build_args_appends_cpu_flag_without_vulkan(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: False)
    w = NcnnUpscaleWrapper("realesrgan")
    w._model = _model_dict(tmp_path, exe_tool="realesrgan", scale=4,
                           cli_model_name="realesrgan-x4plus")
    args = w._build_args(Path("in.png"), Path("out.png"))
    assert args[-2:] == ["-g", "-1"]


# -- enhance (single image) ----------------------------------------------

def _fake_acquire(w, model):
    @contextmanager
    def _acq(model_id=None, variant=None, on_progress=None):
        w._model = model
        yield w
    return _acq


def test_enhance_round_trips_and_checks_output(tmp_path, monkeypatch):
    w = NcnnUpscaleWrapper("realesrgan")
    model = _model_dict(tmp_path, exe_tool="realesrgan", scale=4,
                        cli_model_name="realesrgan-x4plus")
    monkeypatch.setattr(ncnn_upscale, "CliSidecar", _fake_sidecar())
    with patch.object(w, "acquire", _fake_acquire(w, model)):
        result = w.enhance(Image.new("RGB", (64, 64)), model_id="x4plus")
    assert isinstance(result, Image.Image)
    assert result.size == (128, 128)


def test_enhance_raises_when_cli_silently_succeeds_without_output(tmp_path, monkeypatch):
    w = NcnnUpscaleWrapper("realesrgan")
    model = _model_dict(tmp_path, exe_tool="realesrgan", scale=4,
                        cli_model_name="realesrgan-x4plus")

    class _SilentSC:
        def __init__(self, exe, on_line=None, cwd=None):
            pass

        def run(self, args, timeout=None):
            return 0                    # exits 0 but writes nothing

    monkeypatch.setattr(ncnn_upscale, "CliSidecar", _SilentSC)
    with patch.object(w, "acquire", _fake_acquire(w, model)):
        with pytest.raises(SidecarError):
            w.enhance(Image.new("RGB", (64, 64)), model_id="x4plus")


# -- progress accumulation (realesrgan % stream) -------------------------

def test_progress_accumulates_across_dir_mode_images(tmp_path, monkeypatch):
    w = NcnnUpscaleWrapper("realesrgan")
    w._model = _model_dict(tmp_path, exe_tool="realesrgan", scale=4,
                           cli_model_name="realesrgan-x4plus")
    monkeypatch.setattr(ncnn_upscale, "CliSidecar",
                        _fake_sidecar(lines=["50.00%", "100.00%", "10.00%"]))
    out_dir = tmp_path / "out"
    progress = []
    w._run_cli(tmp_path / "in", out_dir, lambda p, m: progress.append(p),
               total_frames=3, base_done=0, timeout=10)
    assert progress == sorted(progress)        # monotonic non-decreasing
    assert all(p > 1.0 for p in progress)      # inference band convention


def test_progress_counts_untiled_frames(tmp_path, monkeypatch):
    # ADVERSARIAL: two single-line "100.00%" frames (no tiling dips) must both
    # be counted — pins count-completions, not dip-detection.
    w = NcnnUpscaleWrapper("realesrgan")
    w._model = _model_dict(tmp_path, exe_tool="realesrgan", scale=4,
                           cli_model_name="realesrgan-x4plus")
    monkeypatch.setattr(ncnn_upscale, "CliSidecar",
                        _fake_sidecar(lines=["100.00%", "100.00%"]))
    out_dir = tmp_path / "out"
    progress = []
    w._run_cli(tmp_path / "in", out_dir, lambda p, m: progress.append(p),
               total_frames=2, base_done=0, timeout=10)
    assert len(progress) == 2
    assert progress[0] == pytest.approx(1.5)
    assert progress[1] > 1.99                  # 2nd frame counted, not frozen


# -- enhance_dir output count + NFR2 lines --------------------------------

def test_enhance_dir_raises_on_short_output_count(tmp_path, monkeypatch):
    w = NcnnUpscaleWrapper("realesrgan")
    model = _model_dict(tmp_path, exe_tool="realesrgan", scale=4,
                        cli_model_name="realesrgan-x4plus")
    monkeypatch.setattr(ncnn_upscale, "CliSidecar", _fake_sidecar(out_files=1))
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    with patch.object(w, "acquire", _fake_acquire(w, model)):
        with pytest.raises(SidecarError, match="1/2"):
            w.enhance_dir(in_dir, out_dir, total_frames=2, model_id="x4plus",
                          chunk_total=2)


def test_device_lines_retained_for_nfr2(tmp_path, monkeypatch):
    w = NcnnUpscaleWrapper("realesrgan")
    w._model = _model_dict(tmp_path, exe_tool="realesrgan", scale=4,
                           cli_model_name="realesrgan-x4plus")
    monkeypatch.setattr(ncnn_upscale, "CliSidecar",
                        _fake_sidecar(lines=["[0 FakeGPU]"]))
    out_dir = tmp_path / "out"
    w._run_cli(tmp_path / "in", out_dir, None, total_frames=1, base_done=0, timeout=10)
    assert any("[0 FakeGPU]" in line for line in w.last_run_lines)
