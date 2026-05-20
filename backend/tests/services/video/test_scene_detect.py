from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.services.video.summary_service.scene_detect import SceneDetector


def test_detect_in_window_returns_scene_timestamps_within_range():
    detector = SceneDetector(ffmpeg=MagicMock())

    fake_scenes = [
        (MagicMock(get_seconds=lambda: 12.0), MagicMock(get_seconds=lambda: 30.0)),
        (MagicMock(get_seconds=lambda: 30.0), MagicMock(get_seconds=lambda: 45.0)),
    ]

    with patch("scenedetect.detect", return_value=fake_scenes) as m:
        result = detector.detect_in_window(Path("dummy.mp4"), 10.0, 50.0)

    assert m.called
    args, kwargs = m.call_args
    assert kwargs.get("start_time") == 10.0
    assert kwargs.get("end_time") == 50.0
    assert result == [12.0, 30.0]


def test_detect_in_window_returns_empty_on_error():
    detector = SceneDetector(ffmpeg=MagicMock())
    with patch("scenedetect.detect", side_effect=RuntimeError("bad")):
        result = detector.detect_in_window(Path("dummy.mp4"), 0.0, 10.0)
    assert result == []


def test_extract_frame_invokes_ffmpeg(tmp_path):
    mock_ffmpeg = MagicMock()
    mock_ffmpeg.extract_frame_sync = MagicMock()
    detector = SceneDetector(ffmpeg=mock_ffmpeg)
    out = tmp_path / "frame.jpg"

    detector.extract_frame(input_path=Path("dummy.mp4"), output_path=out, timestamp=42.5)

    mock_ffmpeg.extract_frame_sync.assert_called_once_with(
        input_path=Path("dummy.mp4"),
        output_path=out,
        timestamp=42.5,
    )


# ── perf/video-summary-bullet-cap-scene-once: detect_all ───────────────
def test_detect_all_one_pass_no_window_kwargs():
    detector = SceneDetector(ffmpeg=MagicMock())
    fake = [
        (MagicMock(get_seconds=lambda: 5.0), MagicMock(get_seconds=lambda: 9.0)),
        (MagicMock(get_seconds=lambda: 9.0), MagicMock(get_seconds=lambda: 20.0)),
    ]
    with patch("scenedetect.detect", return_value=fake) as m:
        result = detector.detect_all(Path("dummy.mp4"))
    assert m.called
    _, kwargs = m.call_args
    assert "start_time" not in kwargs and "end_time" not in kwargs
    assert result == [5.0, 9.0]


def test_detect_all_is_cached():
    detector = SceneDetector(ffmpeg=MagicMock())
    fake = [(MagicMock(get_seconds=lambda: 1.0), MagicMock(get_seconds=lambda: 2.0))]
    with patch("scenedetect.detect", return_value=fake) as m:
        a = detector.detect_all(Path("dummy.mp4"))
        b = detector.detect_all(Path("dummy.mp4"))
    assert a == b == [1.0]
    assert m.call_count == 1  # second call served from cache


def test_detect_all_returns_empty_on_error():
    detector = SceneDetector(ffmpeg=MagicMock())
    with patch("scenedetect.detect", side_effect=RuntimeError("bad")):
        assert detector.detect_all(Path("dummy.mp4")) == []


def test_extract_frame_forwards_max_edge_when_set(tmp_path):
    from unittest.mock import MagicMock
    from pathlib import Path
    from app.services.video.summary_service.scene_detect import SceneDetector

    mock_ffmpeg = MagicMock()
    mock_ffmpeg.extract_frame_sync = MagicMock()
    det = SceneDetector(ffmpeg=mock_ffmpeg)
    out = tmp_path / "f.jpg"

    det.extract_frame(input_path=Path("v.mp4"), output_path=out,
                       timestamp=1.0, max_edge=768)
    mock_ffmpeg.extract_frame_sync.assert_called_once_with(
        input_path=Path("v.mp4"), output_path=out, timestamp=1.0,
        max_edge=768,
    )


def test_extract_frame_omits_max_edge_kwarg_when_none(tmp_path):
    from unittest.mock import MagicMock
    from pathlib import Path
    from app.services.video.summary_service.scene_detect import SceneDetector

    mock_ffmpeg = MagicMock()
    mock_ffmpeg.extract_frame_sync = MagicMock()
    det = SceneDetector(ffmpeg=mock_ffmpeg)
    out = tmp_path / "f.jpg"

    det.extract_frame(input_path=Path("v.mp4"), output_path=out, timestamp=1.0)
    # max_edge must NOT be in the forwarded kwargs (keeps the legacy
    # test_extract_frame_invokes_ffmpeg exact 3-kwarg contract green).
    _, kwargs = mock_ffmpeg.extract_frame_sync.call_args
    assert "max_edge" not in kwargs
