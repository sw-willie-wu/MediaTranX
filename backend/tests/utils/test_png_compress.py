from pathlib import Path
from PIL import Image
from app.utils.png_compress import compress_png

FIX = Path(__file__).parent.parent / "fixtures" / "compress"

def test_lossy_png_shrinks(tmp_path):
    dst = tmp_path / "o.png"
    compress_png(FIX / "sample.png", dst, lossy=True, strength=80)
    assert dst.exists() and dst.stat().st_size < (FIX / "sample.png").stat().st_size

def test_lossless_png_shrinks_or_equal(tmp_path):
    dst = tmp_path / "o.png"
    compress_png(FIX / "sample.png", dst, lossy=False, strength=50)
    assert dst.exists() and dst.stat().st_size <= (FIX / "sample.png").stat().st_size

def test_lossy_low_strength_does_not_crash(tmp_path):
    """Low strength (light compression) must never raise RuntimeError."""
    dst = tmp_path / "o.png"
    compress_png(FIX / "sample.png", dst, lossy=True, strength=0)
    assert dst.exists()
    with Image.open(dst) as im:
        assert im.format == "PNG"
    assert dst.stat().st_size <= (FIX / "sample.png").stat().st_size

def test_lossy_higher_strength_not_larger(tmp_path):
    """Higher strength must produce a file no larger than lower strength."""
    dst_low = tmp_path / "low.png"
    dst_high = tmp_path / "high.png"
    compress_png(FIX / "sample.png", dst_low, lossy=True, strength=20)
    compress_png(FIX / "sample.png", dst_high, lossy=True, strength=100)
    assert dst_high.stat().st_size <= dst_low.stat().st_size
