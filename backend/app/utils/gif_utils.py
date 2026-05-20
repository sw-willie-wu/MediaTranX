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


def apply_and_save(
    raw: "PILImage.Image",
    output_path,
    frame_fn: Callable[["PILImage.Image"], "PILImage.Image"],
    *,
    on_progress=None,
    preserve_alpha: bool = True,
    static_save_kwargs=None,
) -> None:
    """Apply `frame_fn` to a still image or every frame of an animation, then save.

    Detects animation via `animation_format(raw)`. If `preserve_alpha=True`,
    wraps `frame_fn` with `image_alpha.preserve_alpha`. Progress callback
    (optional) is invoked per frame as `((frame_idx + 1) / total, msg_key)` —
    frame_idx is zero-based but we report frames *completed*, so the first
    frame reports `1/total` and the last reports `1.0`.

    Args:
        raw: PIL Image (still or multi-frame)
        output_path: destination path (str or Path)
        frame_fn: per-frame transform `(PIL.Image) -> PIL.Image`
        on_progress: optional `(float, str)` callback, called once per frame in animation path
        preserve_alpha: when True, wrap `frame_fn` with `image_alpha.preserve_alpha`
        static_save_kwargs: forwarded to `Image.save` for static path only
    """
    from app.utils.image_alpha import preserve_alpha as _preserve_alpha

    effective_fn = (
        (lambda img: _preserve_alpha(img, frame_fn)) if preserve_alpha else frame_fn
    )

    fmt = animation_format(raw)
    if fmt:
        total = getattr(raw, "n_frames", 1)

        def _wrapped_frame(img: "PILImage.Image", idx: int, _total: int) -> "PILImage.Image":
            if on_progress:
                on_progress(
                    (idx + 1) / max(total, 1),
                    f"task.progress.processing_frame|{idx + 1}|{total}",
                )
            return effective_fn(img)

        frames = process_gif_frames(raw, _wrapped_frame)
        save_animated(frames, str(output_path), fmt)
    else:
        result = effective_fn(raw)
        result.save(str(output_path), **(static_save_kwargs or {}))
