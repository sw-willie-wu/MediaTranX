from pathlib import Path
from unittest.mock import MagicMock

from app.services.video.summary_service.frame_picker import pick_frame_timestamp


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


# ── fix/video-summary-frame-ts-clamp ────────────────────────────────────
import pytest

from app.services.video.summary_service.frame_picker import _clamp_ts


@pytest.mark.parametrize("t,duration,fps,expected", [
    (-5.0, None, None, 0.0),            # floor at 0 even when clamp disabled
    (0.0, None, None, 0.0),
    (15.0, None, None, 15.0),           # duration None → identity (in range)
    (15.0, 0.0, None, 15.0),            # duration 0.0 → clamp disabled
    (15.0, -1.0, None, 15.0),           # duration < 0 → clamp disabled
    (100.0, 60.0, 30.0, 59.95),         # past EOF, 30fps → margin 0.05
    (100.0, 10.0, 1.0, 8.5),            # low fps → margin 1.5/1=1.5
    (5.0, 60.0, None, 5.0),             # in range, fps None → margin 0.05, identity
    (119.99, 120.0, 30.0, 119.95),      # below duration but inside margin → pulled in
    (120.0, 120.0, 30.0, 119.95),       # == duration
    (10.0, 0.03, 30.0, 0.0),            # duration < margin → 0.0 (valid -ss 0)
])
def test__clamp_ts_boundaries(t, duration, fps, expected):
    assert _clamp_ts(t, duration, fps) == pytest.approx(expected)


def test_pick_clamps_midpoint_when_window_past_duration():
    detector = MagicMock()
    detector.detect_in_window.return_value = []  # → midpoint path
    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=None,
        video_path=Path("x.mp4"),
        window_start=3000.0,
        window_end=3100.0,
        context_text="x",
        duration=2444.0,
        fps=30.0,
    )
    assert result == pytest.approx(2443.95)
    assert result <= 2444.0


def test_pick_clamps_candidate_when_past_duration():
    detector = MagicMock()
    detector.detect_in_window.return_value = [3000.0, 3050.0]  # scenedetect past EOF
    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=None,
        video_path=Path("x.mp4"),
        window_start=2900.0,
        window_end=3100.0,
        context_text="x",
        duration=2444.0,
        fps=30.0,
    )
    assert result <= 2444.0
    assert result == pytest.approx(2443.95)


# ── perf/video-summary-bullet-cap-scene-once: scenes= param ────────────
def test_pick_with_scenes_filters_end_exclusive_no_detect_call():
    detector = MagicMock()
    # scenes provided → detect_in_window must NOT be called
    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=None,
        video_path=Path("x.mp4"),
        window_start=10.0,
        window_end=30.0,
        context_text="x",
        scenes=[5.0, 10.0, 20.0, 30.0, 40.0],  # 30.0 excluded (end-exclusive)
        duration=600.0,
        fps=30.0,
    )
    detector.detect_in_window.assert_not_called()
    # candidates = [10.0, 20.0]; no vlm → nearest to mid(20.0) → 20.0
    assert result == pytest.approx(20.0)


def test_pick_with_scenes_empty_filter_falls_back_to_midpoint():
    detector = MagicMock()
    result = pick_frame_timestamp(
        detector=detector,
        vlm_callback=None,
        video_path=Path("x.mp4"),
        window_start=100.0,
        window_end=110.0,
        context_text="x",
        scenes=[5.0, 10.0, 900.0],  # none in [100,110)
        duration=600.0,
        fps=30.0,
    )
    detector.detect_in_window.assert_not_called()
    assert result == pytest.approx(105.0)  # midpoint, in range → unclamped


def test_pick_scenes_none_still_uses_detect_in_window():
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
    detector.detect_in_window.assert_called_once()
    assert result == 12.3
