"""Unit tests for gif_utils.apply_and_save."""
import pytest
from PIL import Image
from app.utils.gif_utils import apply_and_save


def test_static_rgba_preserves_alpha(tmp_path):
    raw = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
    out = tmp_path / "out.png"
    apply_and_save(raw, out, lambda img: img)
    assert out.exists()
    reloaded = Image.open(out)
    assert reloaded.mode == "RGBA"
    assert reloaded.split()[-1].getpixel((0, 0)) == 128


def test_static_rgb_passthrough(tmp_path):
    raw = Image.new("RGB", (10, 10), (100, 100, 100))
    out = tmp_path / "out.png"
    apply_and_save(raw, out, lambda img: Image.new("RGB", img.size, (0, 0, 255)))
    assert Image.open(out).getpixel((5, 5)) == (0, 0, 255)


def test_static_preserve_alpha_false_bypasses_helper(tmp_path):
    raw = Image.new("RGBA", (10, 10), (255, 0, 0, 100))
    out = tmp_path / "out.png"
    apply_and_save(raw, out, lambda img: img.convert("RGB"), preserve_alpha=False)
    assert Image.open(out).mode == "RGB"


def test_animated_gif_frame_fn_applied_per_frame(tmp_path):
    frames = [Image.new("RGB", (4, 4), (i * 80, 0, 0)) for i in range(3)]
    gif_path = tmp_path / "in.gif"
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=100, loop=0)

    raw = Image.open(gif_path)
    out = tmp_path / "out.gif"
    count = [0]
    def mark(img):
        count[0] += 1
        return img
    apply_and_save(raw, out, mark)
    assert count[0] == 3
    assert out.exists()


def test_progress_callback_monotonic_for_animation(tmp_path):
    frames = [Image.new("RGB", (4, 4), (i * 60, 0, 0)) for i in range(4)]
    gif_path = tmp_path / "in.gif"
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=100, loop=0)

    raw = Image.open(gif_path)
    out = tmp_path / "out.gif"
    progress_calls = []
    apply_and_save(raw, out, lambda img: img, on_progress=lambda p, msg: progress_calls.append(p))
    assert len(progress_calls) == 4
    for a, b in zip(progress_calls, progress_calls[1:]):
        assert b >= a


def test_static_save_kwargs_forwarded(tmp_path):
    raw = Image.new("RGB", (10, 10), (0, 255, 0))
    out = tmp_path / "out.jpg"
    apply_and_save(raw, out, lambda img: img, static_save_kwargs={"quality": 50})
    assert out.exists()
