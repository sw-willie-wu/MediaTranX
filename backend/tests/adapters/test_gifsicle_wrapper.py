from pathlib import Path
import pytest
from PIL import Image
from app.adapters.binary.gifsicle import GifsicleWrapper, GifsicleNotFound, _resolve_gifsicle

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

def test_construction_never_raises_when_unresolvable():
    """DI Singleton construction must succeed even when gifsicle is absent."""
    w = GifsicleWrapper(_resolver=lambda: None)
    assert w._path is None

def test_compress_raises_when_unresolvable(tmp_path):
    """GifsicleNotFound must only fire when GIF compress is actually attempted."""
    w = GifsicleWrapper(_resolver=lambda: None)
    with pytest.raises(GifsicleNotFound):
        w.compress(FIX / "anim.gif", tmp_path / "o.gif")

def test_resolver_falls_back_to_gifsicle_bin_wheel(monkeypatch):
    """Regression test for the packaged-build bug.

    Simulate a PATH that doesn't include the venv Scripts dir
    (as happens under the frozen core.exe) by making shutil.which return None.
    The resolver must still find the binary via the gifsicle_bin wheel derivation.
    """
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = _resolve_gifsicle()
    assert result is not None, (
        "_resolve_gifsicle() returned None even with gifsicle-bin installed; "
        "packaged-build fallback is broken"
    )
    assert Path(result).is_file(), f"Resolved path does not exist: {result}"
    assert "gifsicle" in Path(result).name.lower()
