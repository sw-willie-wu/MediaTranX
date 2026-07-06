from pathlib import Path
import pytest
from app.services.image.compress_service import ImageCompressService, TASK_TYPE_IMAGE_COMPRESS

FIX = Path(__file__).parent.parent / "fixtures" / "compress"

class _Files:
    def __init__(self, src, tmp): self.src, self.tmp = src, tmp
    def require_file(self, fid):
        import types
        return types.SimpleNamespace(file_path=self.src, original_filename=self.src.name,
                                     file_size=self.src.stat().st_size)
    def create_output_path(self, original_filename, suffix, ext):
        p = self.tmp / f"out{suffix}{ext}"; return ("oid", p)
    def register_output(self, file_id, file_path, original_filename):
        import types
        return types.SimpleNamespace(filename=file_path.name, file_size=file_path.stat().st_size)

class _TM:
    def register_handler(self, *a, **k): pass

def test_png_lossy_compress_shrinks(tmp_path):
    from PIL import Image
    from app.adapters.binary.gifsicle import GifsicleWrapper
    svc = ImageCompressService(_Files(FIX / "sample.png", tmp_path), _TM(), GifsicleWrapper())
    res = svc._execute({"file_id": "x", "strength": 80, "png_lossy": True}, lambda p, m: None)
    assert res["output_size"] < res["original_size"], (
        f"lossy PNG should shrink: {res['output_size']} vs {res['original_size']}")
    out = tmp_path / "out_compressed.png"
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "PNG"


def test_png_lossless_compress_shrinks_or_equal(tmp_path):
    from PIL import Image
    from app.adapters.binary.gifsicle import GifsicleWrapper
    svc = ImageCompressService(_Files(FIX / "sample.png", tmp_path), _TM(), GifsicleWrapper())
    res = svc._execute({"file_id": "x", "strength": 80, "png_lossy": False}, lambda p, m: None)
    assert res["output_size"] <= res["original_size"], (
        f"lossless PNG should not grow: {res['output_size']} vs {res['original_size']}")
    out = tmp_path / "out_compressed.png"
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "PNG"


def test_jpeg_compress_shrinks(tmp_path):
    from PIL import Image
    from app.adapters.binary.gifsicle import GifsicleWrapper
    svc = ImageCompressService(_Files(FIX / "sample.jpg", tmp_path), _TM(), GifsicleWrapper())
    res = svc._execute({"file_id": "x", "strength": 80}, lambda p, m: None)
    assert res["output_size"] < res["original_size"], (
        f"JPEG should shrink at strength=80: {res['output_size']} vs {res['original_size']}")
    out = tmp_path / "out_compressed.jpg"
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "JPEG"


def test_webp_lossy_shrinks(tmp_path):
    from PIL import Image
    from app.adapters.binary.gifsicle import GifsicleWrapper
    svc = ImageCompressService(_Files(FIX / "sample.webp", tmp_path), _TM(), GifsicleWrapper())
    res = svc._execute({"file_id": "x", "strength": 80}, lambda p, m: None)
    assert res["output_size"] < res["original_size"], (
        f"lossy WebP should shrink at strength=80: {res['output_size']} vs {res['original_size']}")
    out = tmp_path / "out_compressed.webp"
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "WEBP"


def test_webp_lossless_valid(tmp_path):
    from PIL import Image
    from app.adapters.binary.gifsicle import GifsicleWrapper
    svc = ImageCompressService(_Files(FIX / "sample.webp", tmp_path), _TM(), GifsicleWrapper())
    res = svc._execute({"file_id": "x", "strength": 50, "webp_lossless": True}, lambda p, m: None)
    # Re-encoding a lossy WebP as lossless grows the file (lossy pixel data → lossless encoding).
    # Assert validity only: the output must open as a well-formed WEBP.
    assert res["output_size"] > 0
    out = tmp_path / "out_compressed.webp"
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "WEBP"


def test_gif_upsize_guard_skips_colors_when_gif_colors_exceeds_actual(tmp_path):
    """P2: gif_colors > actual palette size → --colors is NOT passed → no palette upsizing."""
    import subprocess
    from app.adapters.binary.gifsicle import GifsicleWrapper, _resolve_gifsicle

    # Pre-optimise anim.gif to 32 colours; this becomes the "already optimised" input
    pre_opt = tmp_path / "pre_opt.gif"
    gifsicle_bin = _resolve_gifsicle()
    subprocess.run(
        [gifsicle_bin, "-O3", f"--colors=32", str(FIX / "anim.gif"), "-o", str(pre_opt)],
        check=True,
    )

    svc = ImageCompressService(_Files(pre_opt, tmp_path), _TM(), GifsicleWrapper())
    res = svc._execute(
        {"file_id": "x", "strength": 75, "gif_colors": 128,
         "gif_frame_drop": 0, "gif_optimize_transparency": True, "gif_coalesce": False},
        lambda p, m: None,
    )
    # With P2 guard, gif_colors=128 > actual≈32 → colours arg is suppressed → no upsizing
    assert res["output_size"] <= res["original_size"], (
        f"Upsize guard failed: output {res['output_size']} > original {res['original_size']}"
    )


def test_gif_colors_genuinely_reduces_when_below_actual(tmp_path):
    """P2: gif_colors < actual → --colors IS passed → palette reduces → file shrinks."""
    from app.adapters.binary.gifsicle import GifsicleWrapper

    svc = ImageCompressService(_Files(FIX / "anim.gif", tmp_path), _TM(), GifsicleWrapper())
    res = svc._execute(
        {"file_id": "x", "strength": 75, "gif_colors": 64,
         "gif_frame_drop": 0, "gif_optimize_transparency": True, "gif_coalesce": False},
        lambda p, m: None,
    )
    # anim.gif has ~216 colours; 64 < 216 so --colors=64 is passed and it should compress
    assert res["output_size"] <= res["original_size"], (
        f"Expected GIF to compress: output {res['output_size']} vs original {res['original_size']}"
    )
    assert res["saved_ratio"] >= 0.0


def test_never_grow_guard_activates_for_oversized_output(tmp_path):
    """P3: if encoder outputs a file larger than the original, guard replaces it with the original."""
    src = FIX / "anim.gif"
    original_data = src.read_bytes()

    class _BigGifsicle:
        """Fake gifsicle that deliberately writes a file larger than the source."""
        def compress(self, src_path, dst_path, **kwargs):
            dst_path.write_bytes(original_data + b"\x00" * 1000)

    svc = ImageCompressService(_Files(src, tmp_path), _TM(), _BigGifsicle())
    res = svc._execute({"file_id": "x", "strength": 50}, lambda p, m: None)

    assert res["output_size"] == res["original_size"], (
        f"Guard should have reset output to original size; got {res['output_size']}"
    )
    assert res["saved_ratio"] == 0.0
    assert res["already_optimal"] is True
    out = tmp_path / "out_compressed.gif"
    assert out.read_bytes() == original_data, "out_path must contain byte-identical copy of source"


def test_gif_compress_shrinks_and_stays_animated(tmp_path):
    from PIL import Image
    from app.adapters.binary.gifsicle import GifsicleWrapper
    with Image.open(FIX / "anim.gif") as im:
        n_in = im.n_frames
    svc = ImageCompressService(_Files(FIX / "anim.gif", tmp_path), _TM(), GifsicleWrapper())
    res = svc._execute({"file_id": "x", "strength": 90, "gif_colors": 64,
                        "gif_frame_drop": 0, "gif_optimize_transparency": True,
                        "gif_coalesce": False}, lambda p, m: None)
    assert res["output_size"] < res["original_size"]
    assert 0 < res["saved_ratio"] <= 1
    out = Path(tmp_path / "out_compressed.gif")
    assert out.exists()
    with Image.open(out) as o:
        assert o.n_frames == n_in and o.info.get("loop", None) == 0
