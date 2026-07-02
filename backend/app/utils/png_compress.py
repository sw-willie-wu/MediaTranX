"""PNG compression: lossy via libimagequant (imagequant), lossless via oxipng."""
from pathlib import Path
from PIL import Image
import imagequant
import oxipng


def _quality_window(strength: int) -> tuple[int, int]:
    s = max(0, min(100, strength))
    max_q = max(20, 100 - int(s * 0.7))
    min_q = max(0, max_q - 40)
    return min_q, max_q


def compress_png(src: Path, dst: Path, *, lossy: bool, strength: int) -> None:
    if lossy:
        min_q, max_q = _quality_window(strength)
        with Image.open(src) as im:
            im = im.convert("RGBA")
            out = imagequant.quantize_pil_image(
                im, dithering_level=1.0, max_colors=256,
                min_quality=min_q, max_quality=max_q,
            )
            out.save(dst, format="PNG")
        oxipng.optimize(str(dst), str(dst), level=4)
    else:
        level = 2 + min(4, strength // 25)  # 2..6
        oxipng.optimize(str(src), str(dst), level=level)
