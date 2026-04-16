from pathlib import Path
from unittest.mock import MagicMock

from app.services.video._frame_picker import pick_frame_timestamp


def test_pick_returns_middle_when_no_scenes():
    detector = MagicMock()
    detector.detect_in_window.return_value = []

    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=None,
        video_path=Path("x.mp4"),
        window_start=10.0,
        window_end=20.0,
        context_text="x",
    )
    assert result == 15.0  # middle


def test_pick_returns_only_scene_when_one():
    detector = MagicMock()
    detector.detect_in_window.return_value = [12.3]

    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=None,
        video_path=Path("x.mp4"),
        window_start=10.0,
        window_end=20.0,
        context_text="x",
    )
    assert result == 12.3


def test_pick_uses_vlm_when_multiple_and_vlm_available(tmp_path):
    detector = MagicMock()
    detector.detect_in_window.return_value = [12.0, 15.0, 18.0]
    detector.extract_frame = MagicMock()

    vlm = MagicMock(return_value=1)  # picks index 1 → 15.0

    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=vlm,
        video_path=Path("x.mp4"),
        window_start=10.0,
        window_end=20.0,
        context_text="段落文字",
        temp_dir=tmp_path,
    )
    assert result == 15.0
    assert detector.extract_frame.call_count == 3
    vlm.assert_called_once()


def test_pick_returns_midpoint_nearest_when_multiple_but_no_vlm():
    detector = MagicMock()
    detector.detect_in_window.return_value = [12.0, 15.0, 18.0]

    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=None,
        video_path=Path("x.mp4"),
        window_start=10.0,
        window_end=20.0,
        context_text="x",
    )
    # Without VLM: pick scene change closest to window middle (15.0)
    assert result == 15.0


def test_pick_falls_back_when_vlm_raises(tmp_path):
    detector = MagicMock()
    detector.detect_in_window.return_value = [12.0, 15.0, 18.0]

    def bad_vlm(*args, **kwargs):
        raise RuntimeError("VLM unavailable")

    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=bad_vlm,
        video_path=Path("x.mp4"),
        window_start=10.0,
        window_end=20.0,
        context_text="x",
        temp_dir=tmp_path,
    )
    # Fallback: midpoint-nearest
    assert result == 15.0


def test_pick_clamps_out_of_range_vlm_index(tmp_path):
    detector = MagicMock()
    detector.detect_in_window.return_value = [12.0, 15.0]
    vlm = MagicMock(return_value=99)  # out of range

    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=vlm,
        video_path=Path("x.mp4"),
        window_start=10.0,
        window_end=20.0,
        context_text="x",
        temp_dir=tmp_path,
    )
    # Clamped to last valid index → 15.0
    assert result == 15.0
