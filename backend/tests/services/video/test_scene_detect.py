from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.services.video.summary_service.scene_detect import SceneDetector


def test_detect_in_window_returns_scene_timestamps_within_range():
    detector = SceneDetector()

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
    detector = SceneDetector()
    with patch("scenedetect.detect", side_effect=RuntimeError("bad")):
        result = detector.detect_in_window(Path("dummy.mp4"), 0.0, 10.0)
    assert result == []


def test_extract_frame_invokes_ffmpeg(tmp_path):
    detector = SceneDetector()
    out = tmp_path / "frame.jpg"

    mock_ffmpeg = MagicMock()
    mock_ffmpeg.extract_frame_sync = MagicMock()
    detector._ffmpeg = mock_ffmpeg  # inject

    detector.extract_frame(input_path=Path("dummy.mp4"), output_path=out, timestamp=42.5)

    mock_ffmpeg.extract_frame_sync.assert_called_once_with(
        input_path=Path("dummy.mp4"),
        output_path=out,
        timestamp=42.5,
    )
