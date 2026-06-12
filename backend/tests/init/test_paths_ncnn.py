"""PathSettings.ncnn returns the bin/ncnn directory (mirrors the llama field)."""
from pathlib import Path

from app.init.configs.paths import PathSettings


def test_ncnn_is_bin_ncnn_directory():
    ps = PathSettings(root=Path("/data"))
    assert ps.ncnn == Path("/data") / "bin" / "ncnn"


def test_ncnn_is_a_directory_not_an_exe():
    # Wrapper finds the per-tool exe inside (bin/ncnn/<tool>/), never an exe path.
    ps = PathSettings(root=Path("/data"))
    assert ps.ncnn.suffix == ""
