"""Tests for gif_colors.count_gif_colors utility."""
from pathlib import Path

import pytest
from PIL import Image

from app.utils.gif_colors import count_gif_colors

FIX = Path(__file__).parent.parent / "fixtures" / "compress"


@pytest.fixture(scope="module")
def large_sharp_gif(tmp_path_factory) -> Path:
    """4 frames of 800x800 (2.56M px total, > budget in tests) with
    high-frequency adjacent contrasting colors (1px checkerboard of a
    16-color palette). Interpolating resize would blend neighbors and
    invent new colors (overestimate); NEAREST/stride must not."""
    palette = [(i * 16, 255 - i * 16, (i * 32) % 256) for i in range(16)]
    frames = []
    for f in range(4):
        img = Image.new("RGB", (800, 800))
        px = img.load()
        for y in range(800):
            for x in range(800):
                px[x, y] = palette[(x + y + f) % 16]
        frames.append(img)
    out = tmp_path_factory.mktemp("gifcolors") / "large_sharp.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], loop=0)
    return out


def test_count_gif_colors_returns_valid_range():
    """anim.gif has 6 frames with disposal=2; frame modes differ (P then RGB).
    The util must convert each frame to RGB before unioning to avoid garbage values."""
    n = count_gif_colors(FIX / "anim.gif")
    assert isinstance(n, int)
    assert 2 <= n <= 256, f"Expected 2–256 distinct colors, got {n}"


def test_count_gif_colors_never_exceeds_256():
    """Result must never exceed the GIF palette limit of 256."""
    n = count_gif_colors(FIX / "anim.gif")
    assert n <= 256


def test_approx_equals_exact_for_small_gif():
    """Total pixels of anim.gif are far below budget → sampling never
    triggers → result must be IDENTICAL to exact mode."""
    exact = count_gif_colors(FIX / "anim.gif")
    approx = count_gif_colors(FIX / "anim.gif", max_sample_pixels=50_000_000)
    assert approx == exact


def test_approx_never_overestimates_on_large_sharp_gif(large_sharp_gif):
    """Budget forces the sampling path on a sharp-edge fixture where
    interpolating resize demonstrably invents colors. NEAREST/stride
    must yield a value <= exact (strict subset of existing colors)."""
    exact = count_gif_colors(large_sharp_gif)
    approx = count_gif_colors(large_sharp_gif, max_sample_pixels=100_000)
    assert approx <= exact
    assert approx >= 2  # still a sane count


def test_interpolating_resize_would_overestimate(large_sharp_gif):
    """Guard that the fixture actually distinguishes NEAREST from
    interpolation: BILINEAR downscale on this fixture creates NEW colors.
    (If this stops holding, the fixture no longer protects C1.)"""
    from PIL import ImageSequence

    with Image.open(large_sharp_gif) as im:
        frame = next(ImageSequence.Iterator(im)).convert("RGB")
        src_colors = set(frame.getdata())
        small = frame.resize((frame.width // 5, frame.height // 5), Image.BILINEAR)
        blended = set(small.getdata())
    assert not blended.issubset(src_colors), (
        "BILINEAR should invent colors on a 1px checkerboard; "
        "fixture no longer exercises the interpolation hazard"
    )
