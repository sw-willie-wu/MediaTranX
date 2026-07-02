from pathlib import Path
import pytest
from PIL import Image
from app.adapters.binary.gifsicle import GifsicleWrapper, GifsicleNotFound

FIX = Path(__file__).parent.parent / "fixtures" / "compress"

def test_build_args_lossy_and_optimize():
    w = GifsicleWrapper(gifsicle_path="gifsicle")
    args = w.build_args(Path("in.gif"), Path("out.gif"), lossy=80, colors=128,
                        frame_select=[], optimize_transparency=True, coalesce=False)
    assert args[0] == "gifsicle"
    assert "-O3" in args and "--lossy=80" in args and "--colors=128" in args
    assert "in.gif" in args and args[-2:] == ["-o", "out.gif"]
    assert not any(a.startswith("--disposal") for a in args)
    assert "--no-extensions" not in args

def test_optimize_transparency_off_uses_O2():
    w = GifsicleWrapper(gifsicle_path="gifsicle")
    args = w.build_args(Path("in.gif"), Path("out.gif"), lossy=0, colors=None,
                        frame_select=[], optimize_transparency=False, coalesce=False)
    assert "-O2" in args and "-O3" not in args

def test_coalesce_uses_unoptimize():
    w = GifsicleWrapper(gifsicle_path="gifsicle")
    args = w.build_args(Path("in.gif"), Path("out.gif"), lossy=0, colors=None,
                        frame_select=[], optimize_transparency=False, coalesce=True)
    assert "--unoptimize" in args

def test_real_compress_shrinks_and_preserves_animation(tmp_path):
    w = GifsicleWrapper()
    dst = tmp_path / "out.gif"
    with Image.open(FIX / "anim.gif") as im:
        n_in = im.n_frames
    w.compress(FIX / "anim.gif", dst, lossy=100, colors=64, frame_drop=0,
               optimize_transparency=True, coalesce=False)
    assert dst.exists() and dst.stat().st_size < (FIX / "anim.gif").stat().st_size
    with Image.open(dst) as out:
        assert out.n_frames == n_in
        assert out.info.get("loop", None) == 0

def test_frame_drop_reduces_frame_count(tmp_path):
    w = GifsicleWrapper()
    dst = tmp_path / "out.gif"
    with Image.open(FIX / "anim.gif") as im:
        n_in = im.n_frames
    w.compress(FIX / "anim.gif", dst, frame_drop=2)
    with Image.open(dst) as out:
        assert out.n_frames < n_in

def test_missing_binary_raises():
    with pytest.raises(GifsicleNotFound):
        GifsicleWrapper(gifsicle_path=None, _which=lambda _n: None)
