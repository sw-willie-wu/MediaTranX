"""Utility for counting distinct colors in a GIF image."""
from pathlib import Path
from PIL import Image, ImageSequence


def count_gif_colors(path) -> int:
    """Distinct colors actually used across all frames of a (possibly animated) GIF, capped at 256.

    NOTE: PIL returns heterogeneous frame modes for animated GIFs (frame0='P', later frames 'RGB'
    due to disposal), so each frame MUST be convert('RGB')ed before unioning — do NOT union raw
    getdata() (mixes palette ints with RGB tuples → garbage).
    """
    colors: set = set()
    with Image.open(path) as im:
        for frame in ImageSequence.Iterator(im):
            colors |= set(frame.convert("RGB").getdata())
            if len(colors) > 256:
                return 256
    return min(len(colors), 256)
