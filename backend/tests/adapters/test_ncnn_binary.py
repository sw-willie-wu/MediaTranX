"""NcnnVulkan binary adapter (adapters/binary/ncnn.py): arg skeleton, CPU
fallback, single-image + directory round-trips, output checks, progress-band
plumbing, and NFR2 device-line capture.

Seams: patch `app.adapters.binary.ncnn.CliSidecar` (the subprocess engine) and
`NcnnVulkan.exe_path` (no installed exe in CI), plus the SOURCE
`app.adapters.device.has_vulkan` (imported lazily inside `_build_args`).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.adapters.binary import ncnn as ncnn_mod
from app.adapters.binary.ncnn import NcnnVulkan
from app.adapters.binary.sidecar import SidecarError


def _fake_sidecar(lines=(), out_files=1):
    """CliSidecar stand-in: emits `lines`, then writes output PNG(s) at `-o`."""
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


def _nv(monkeypatch, lines=(), out_files=1):
    nv = NcnnVulkan("realesrgan", "realesrgan-ncnn-vulkan")
    monkeypatch.setattr(nv, "exe_path", lambda: "exe")          # no installed exe
    monkeypatch.setattr(ncnn_mod, "CliSidecar", _fake_sidecar(lines, out_files))
    return nv


# -- _build_args ----------------------------------------------------------

def test_build_args_skeleton_and_flags(monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    nv = NcnnVulkan("realesrgan", "realesrgan-ncnn-vulkan")
    md = Path("md")
    args = nv._build_args(Path("in.png"), Path("out.png"), md, 4, ["-n", "x4plus"])
    assert args[:10] == ["-i", "in.png", "-o", "out.png", "-m", str(md),
                         "-s", "4", "-f", "png"]
    assert args[-2:] == ["-n", "x4plus"]
    assert "-g" not in args                # vulkan present → no CPU flag


def test_build_args_cpu_flag_without_vulkan(monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: False)
    nv = NcnnVulkan("waifu2x", "waifu2x-ncnn-vulkan")
    args = nv._build_args(Path("in.png"), Path("out.png"), Path("md"), 2,
                          ["-n", "-1", "-v"])
    assert args[-2:] == ["-g", "-1"]


# -- upscale_image / upscale_dir ------------------------------------------

def test_upscale_image_round_trips_and_checks_output(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    nv = _nv(monkeypatch)
    out = nv.upscale_image(Image.new("RGB", (64, 64)), tmp_path, 4, ["-n", "x4plus"])
    assert isinstance(out, Image.Image) and out.size == (128, 128)


def test_upscale_image_raises_when_cli_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    nv = NcnnVulkan("realesrgan", "realesrgan-ncnn-vulkan")
    monkeypatch.setattr(nv, "exe_path", lambda: "exe")

    class _SilentSC:
        def __init__(self, exe, on_line=None, cwd=None): ...
        def run(self, args, timeout=None): return 0   # exits 0, writes nothing
    monkeypatch.setattr(ncnn_mod, "CliSidecar", _SilentSC)
    with pytest.raises(SidecarError):
        nv.upscale_image(Image.new("RGB", (64, 64)), tmp_path, 4, ["-n", "x"])


def test_upscale_dir_raises_on_short_output_count(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    nv = _nv(monkeypatch, out_files=1)
    in_dir = tmp_path / "in"; in_dir.mkdir()
    with pytest.raises(SidecarError, match="1/2"):
        nv.upscale_dir(in_dir, tmp_path / "out", tmp_path, 4, ["-n", "x"],
                       total_frames=2, chunk_total=2)


# -- progress band + NFR2 lines -------------------------------------------

def test_run_wraps_parser_fraction_into_inference_band(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    nv = _nv(monkeypatch, lines=["tick"])
    seen = []
    # trivial parser: any line → fraction 0.5, fixed message
    parser = lambda line, state, base, total: (0.5, "task.progress.x")
    nv.upscale_image(Image.new("RGB", (8, 8)), tmp_path, 4, ["-n", "x"],
                     progress_parser=parser, on_progress=lambda p, m: seen.append((p, m)))
    assert seen == [(1.5, "task.progress.x")]      # 1.0 + min(0.5, 0.999)


def test_device_lines_retained_for_nfr2(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.device.has_vulkan", lambda: True)
    nv = _nv(monkeypatch, lines=["[0 FakeGPU]  queueC=2"])
    nv.upscale_image(Image.new("RGB", (8, 8)), tmp_path, 4, ["-n", "x"])
    assert any("[0 FakeGPU]" in line for line in nv.last_run_lines)
