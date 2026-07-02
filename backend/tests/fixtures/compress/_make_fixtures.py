"""Generate tiny, deliberately-compressible fixture images for compress tests."""
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).parent

def _noisy(w=160, h=120):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 13) % 256)
    return img

def main():
    base = _noisy()
    base.save(HERE / "sample.jpg", quality=95)
    base.save(HERE / "sample.png")
    base.save(HERE / "sample.webp", quality=95)
    frames = []
    for i in range(6):
        f = _noisy().copy()
        ImageDraw.Draw(f).rectangle([i * 10, 0, i * 10 + 30, 40], fill=(255, 0, 0))
        frames.append(f.convert("P"))
    frames[0].save(HERE / "anim.gif", save_all=True, append_images=frames[1:],
                   duration=100, loop=0, disposal=2)

if __name__ == "__main__":
    main()
