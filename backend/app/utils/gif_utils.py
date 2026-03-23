"""
Utilities for handling animated GIF and APNG frame-by-frame.
All PIL imports are lazy to comply with the lazy-import rule.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PIL import Image as PILImage


def is_animated(img: "PILImage.Image") -> bool:
    """Return True if the PIL image has more than one frame (GIF or APNG)."""
    try:
        img.seek(1)
        img.seek(0)
        return True
    except EOFError:
        return False


def animation_format(img: "PILImage.Image") -> str | None:
    """
    Return the animation format string if animated, else None.
    Returns "GIF" or "PNG" (for APNG).
    """
    if not is_animated(img):
        return None
    return img.format or "GIF"


def extract_frames(img: "PILImage.Image") -> list[tuple["PILImage.Image", int]]:
    """
    Extract every frame from an animated GIF or APNG.
    Returns list of (frame_copy, duration_ms).
    """
    frames: list[tuple[PILImage.Image, int]] = []
    try:
        while True:
            duration = img.info.get("duration", 100)
            frames.append((img.copy(), int(duration)))
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    return frames


def save_animated_gif(
    frames_and_durations: list[tuple["PILImage.Image", int]],
    output_path: Path | str,
) -> None:
    """Save frames as an animated GIF."""
    if not frames_and_durations:
        return
    images = [f[0].convert("RGBA") for f in frames_and_durations]
    durations = [f[1] for f in frames_and_durations]
    images[0].save(
        str(output_path),
        format="GIF",
        save_all=True,
        append_images=images[1:],
        loop=0,
        duration=durations,
        disposal=2,
    )


def save_animated_png(
    frames_and_durations: list[tuple["PILImage.Image", int]],
    output_path: Path | str,
) -> None:
    """Save frames as an animated PNG (APNG)."""
    if not frames_and_durations:
        return
    images = [f[0].convert("RGBA") for f in frames_and_durations]
    durations = [f[1] for f in frames_and_durations]
    images[0].save(
        str(output_path),
        format="PNG",
        save_all=True,
        append_images=images[1:],
        loop=0,
        duration=durations,
    )


def save_animated(
    frames_and_durations: list[tuple["PILImage.Image", int]],
    output_path: Path | str,
    fmt: str,
) -> None:
    """Save animated frames using the correct format (GIF or PNG/APNG)."""
    if fmt == "PNG":
        save_animated_png(frames_and_durations, output_path)
    else:
        save_animated_gif(frames_and_durations, output_path)


def animation_ext(fmt: str) -> str:
    """Return the file extension for an animation format."""
    return ".png" if fmt == "PNG" else ".gif"


def process_gif_frames(
    img: "PILImage.Image",
    process_fn: Callable[["PILImage.Image", int, int], "PILImage.Image"],
) -> list[tuple["PILImage.Image", int]]:
    """
    Apply process_fn to every frame of an animated GIF or APNG.

    process_fn(frame, frame_index, total_frames) -> processed_frame
    Returns list of (processed_frame, duration_ms).
    """
    frames = extract_frames(img)
    total = len(frames)
    result: list[tuple[PILImage.Image, int]] = []
    for i, (frame, duration) in enumerate(frames):
        processed = process_fn(frame, i, total)
        result.append((processed, duration))
    return result
