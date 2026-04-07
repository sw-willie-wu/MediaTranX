"""Tests for FramePipe — utils/video_frames.py."""
import pytest
from fractions import Fraction

from app.utils.video_frames import FramePipe


class TestFramePipeConstructor:
    """Test FramePipe accepts input/output dimensions and Fraction fps."""

    def test_separate_input_output_dims(self):
        pipe = FramePipe(
            "in.mp4", "out.mp4",
            output_fps=30.0,
            input_width=1920, input_height=1080,
            output_width=3840, output_height=2160,
        )
        assert pipe.input_width == 1920
        assert pipe.input_height == 1080
        assert pipe.output_width == 3840
        assert pipe.output_height == 2160
        assert pipe._frame_size == 1920 * 1080 * 3

    def test_same_dims(self):
        pipe = FramePipe(
            "in.mp4", "out.mp4",
            output_fps=60.0,
            input_width=1280, input_height=720,
            output_width=1280, output_height=720,
        )
        assert pipe.input_width == pipe.output_width
        assert pipe._frame_size == 1280 * 720 * 3

    def test_fraction_fps(self):
        fps = Fraction(60000, 1001)
        pipe = FramePipe(
            "in.mp4", "out.mp4",
            output_fps=fps,
            input_width=1920, input_height=1080,
            output_width=1920, output_height=1080,
        )
        assert pipe.output_fps == Fraction(60000, 1001)
        assert float(pipe.output_fps) == pytest.approx(59.94, abs=0.01)

    def test_float_fps_converted_to_fraction(self):
        pipe = FramePipe(
            "in.mp4", "out.mp4",
            output_fps=30.0,
            input_width=640, input_height=480,
            output_width=640, output_height=480,
        )
        assert isinstance(pipe.output_fps, Fraction)
        assert float(pipe.output_fps) == 30.0

    def test_fraction_target_fps(self):
        pipe = FramePipe(
            "in.mp4", "out.mp4",
            output_fps=Fraction(60000, 1001),
            input_width=640, input_height=480,
            output_width=640, output_height=480,
            target_fps=Fraction(30000, 1001),
        )
        assert isinstance(pipe.target_fps, Fraction)

    def test_fraction_multiplication_precision(self):
        """Verify Fraction avoids float precision issues."""
        source = Fraction(30000, 1001)
        doubled = source * 2
        assert doubled == Fraction(60000, 1001)
        assert doubled.numerator == 60000
        assert doubled.denominator == 1001

    def test_keyword_only_dims(self):
        """input/output width/height must be keyword arguments."""
        with pytest.raises(TypeError):
            FramePipe("in.mp4", "out.mp4", 30.0, 1920, 1080, 3840, 2160)
