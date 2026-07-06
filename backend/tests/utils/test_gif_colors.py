"""Tests for gif_colors.count_gif_colors utility."""
from pathlib import Path

from app.utils.gif_colors import count_gif_colors

FIX = Path(__file__).parent.parent / "fixtures" / "compress"


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
