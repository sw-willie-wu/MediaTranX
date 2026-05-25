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


# ── perf/detect-all-ffmpeg-scene: detect_all delegates to FFmpeg ───────
def test_detect_all_delegates_to_ffmpeg():
    mock_ffmpeg = MagicMock()
    mock_ffmpeg.detect_scenes_sync.return_value = [5.0, 9.0, 20.0]
    detector = SceneDetector(ffmpeg=mock_ffmpeg)
    result = detector.detect_all(Path("dummy.mp4"))
    assert result == [5.0, 9.0, 20.0]
    mock_ffmpeg.detect_scenes_sync.assert_called_once()


def test_detect_all_is_cached():
    mock_ffmpeg = MagicMock()
    mock_ffmpeg.detect_scenes_sync.return_value = [1.0]
    detector = SceneDetector(ffmpeg=mock_ffmpeg)
    a = detector.detect_all(Path("dummy.mp4"))
    b = detector.detect_all(Path("dummy.mp4"))
    assert a == b == [1.0]
    assert mock_ffmpeg.detect_scenes_sync.call_count == 1  # 2nd call cached


def test_detect_all_returns_empty_on_error():
    mock_ffmpeg = MagicMock()
    mock_ffmpeg.detect_scenes_sync.side_effect = RuntimeError("bad")
    detector = SceneDetector(ffmpeg=mock_ffmpeg)
    assert detector.detect_all(Path("dummy.mp4")) == []


def test_detect_all_reraises_cancellation():
    from app.handler.exceptions import TaskCancelledError
    mock_ffmpeg = MagicMock()
    mock_ffmpeg.detect_scenes_sync.side_effect = TaskCancelledError("cancel")
    detector = SceneDetector(ffmpeg=mock_ffmpeg)
    with pytest.raises(TaskCancelledError):
        detector.detect_all(Path("dummy.mp4"))


def test_detect_all_forwards_on_progress():
    mock_ffmpeg = MagicMock()
    mock_ffmpeg.detect_scenes_sync.return_value = []
    detector = SceneDetector(ffmpeg=mock_ffmpeg)

    def cb(_frac):
        pass

    detector.detect_all(Path("dummy.mp4"), on_progress=cb)
    _, kwargs = mock_ffmpeg.detect_scenes_sync.call_args
    assert kwargs["on_progress"] is cb


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


# ── 2026-05-25: drop static cap, OS scheduler does balancing via priority ──
def test_detect_all_does_not_pass_threads_kwarg():
    """detect_all forwards no `threads=` to ffmpeg (let ffmpeg/dav1d auto-pick).

    See spec 2026-05-25-detect-priority-class.md §AC#2 — DETECT_THREAD_CAP
    was removed in favor of Windows BELOW_NORMAL priority + unbounded threads.
    """
    ffmpeg = MagicMock()
    ffmpeg.detect_scenes_sync.return_value = []
    d = SceneDetector(ffmpeg=ffmpeg)
    d.detect_all(Path("v.mp4"))
    kw = ffmpeg.detect_scenes_sync.call_args.kwargs
    assert "threads" not in kw, f"threads kwarg should not be passed (got {kw})"
