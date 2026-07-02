"""PNG compression: lossy via libimagequant (imagequant), lossless via oxipng."""
from pathlib import Path
from PIL import Image
import imagequant
import oxipng


def _lossy_params(strength: int) -> tuple[int, int]:
    """Return (max_quality, max_colors) for the lossy path.

    min_quality is always 0 to prevent RuntimeError on complex images at low
    strength.  max_colors scales down with strength so the slider is observable.
    """
    s = max(0, min(100, strength))
    max_q = max(20, 100 - int(s * 0.7))       # 100 -> 30
    colors = max(16, 256 - int(s * 2.24))      # 256 -> ~32
    return max_q, colors


def compress_png(src: Path, dst: Path, *, lossy: bool, strength: int) -> None:
    if lossy:
        max_q, colors = _lossy_params(strength)
        with Image.open(src) as im:
            im = im.convert("RGBA")
            out = imagequant.quantize_pil_image(
                im, dithering_level=1.0, max_colors=colors,
                min_quality=0, max_quality=max_q,
            )
            out.save(dst, format="PNG")
        oxipng.optimize(str(dst), str(dst), level=4)
    else:
        level = 2 + min(4, strength // 25)  # 2..6
        oxipng.optimize(str(src), str(dst), level=level)
