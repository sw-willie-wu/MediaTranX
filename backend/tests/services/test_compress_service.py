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
