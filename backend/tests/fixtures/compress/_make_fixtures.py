"""Generate fixture images for compress tests.

sample.png  — 480x360 truecolor smooth-gradient + mild random noise.
              Many unique colours → large PNG; palette-reducible by imagequant.
sample.jpg / sample.webp / anim.gif — kept small (160x120) for speed.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
RNG = np.random.default_rng(42)


def _gradient_noise(w: int = 480, h: int = 360) -> Image.Image:
    """Smooth RGB gradient + per-pixel noise → real truecolor content."""
    xs = np.linspace(0, 255, w, dtype=np.float32)
    ys = np.linspace(0, 255, h, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)           # shape (h, w)

    r = np.clip(xg, 0, 255).astype(np.uint8)
    g = np.clip(yg, 0, 255).astype(np.uint8)
    b = np.clip(255 - xg * 0.5 - yg * 0.5, 0, 255).astype(np.uint8)

    noise = RNG.integers(-18, 19, (h, w, 3), dtype=np.int16)
    rgb = np.stack([r, g, b], axis=-1).astype(np.int16) + noise
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def _periodic(w: int = 160, h: int = 120) -> Image.Image:
    """Original cheap periodic pattern — stays for jpg/webp/gif fixtures."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 13) % 256)
    return img


def main() -> None:
    small = _periodic()
    small.save(HERE / "sample.jpg", quality=95)
    small.save(HERE / "sample.webp", quality=95)

    large = _gradient_noise()
    large.save(HERE / "sample.png")

    frames = []
    for i in range(6):
        f = _periodic().copy()
        ImageDraw.Draw(f).rectangle([i * 10, 0, i * 10 + 30, 40], fill=(255, 0, 0))
        frames.append(f.convert("P"))
    frames[0].save(
        HERE / "anim.gif",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
        disposal=2,
    )
    print("Fixtures written to", HERE)
    import os
    for name in ("sample.png", "sample.jpg", "sample.webp", "anim.gif"):
        path = HERE / name
        print(f"  {name}: {os.path.getsize(path):,} bytes")


if __name__ == "__main__":
    main()
