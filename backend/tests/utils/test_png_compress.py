from pathlib import Path
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
