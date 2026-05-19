from fractions import Fraction
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.services.video.summary_service import VideoSummaryService
from app.services.video.summary_service.service import TASK_TYPE_VIDEO_SUMMARY
from app.handler.exceptions import FileNotFoundError_
from app.adapters.binary.ffmpeg import MediaInfo


def _media_info(duration: float = 120.0, fps: float = 30.0) -> MediaInfo:
    return MediaInfo(
        duration=duration, width=1920, height=1080, fps=fps,
        fps_fraction=Fraction(30, 1), video_codec="h264",
        audio_codec="aac", bitrate=1000, file_size=1,
    )


def test_service_registers_handler():
    ffmpeg = MagicMock()
    file_service = MagicMock()
    task_manager = MagicMock()
    chat_service = MagicMock()

    svc = VideoSummaryService(
        ffmpeg=ffmpeg,
        file_service=file_service,
        task_manager=task_manager,
        chat_service=chat_service,
        model_manager=MagicMock(),
        whisper=MagicMock(),
        demucs=MagicMock(),
        alignment_engine=MagicMock(),
    )
    assert svc is not None
    task_manager.register_handler.assert_called_once()
    args, kwargs = task_manager.register_handler.call_args
    assert args[0] == TASK_TYPE_VIDEO_SUMMARY
    assert kwargs.get("output_policy") == "results"


@pytest.mark.asyncio
async def test_submit_summary_validates_file_exists():
    ffmpeg = MagicMock()
    file_service = MagicMock()
    file_service.require_file.side_effect = FileNotFoundError_("File not found: nonexistent")
    task_manager = MagicMock()

    svc = VideoSummaryService(
        ffmpeg=ffmpeg,
        file_service=file_service,
        task_manager=task_manager,
        chat_service=MagicMock(),
        model_manager=MagicMock(),
        whisper=MagicMock(),
        demucs=MagicMock(),
        alignment_engine=MagicMock(),
    )
    with pytest.raises(FileNotFoundError_, match="File not found"):
        await svc.submit_summary(
            file_id="nonexistent",
            llm_model_family="qwen3.5",
            llm_model_size="9b",
            language="zh-TW",
        )


def _make_svc_with_mocks(tmp_path):
    ffmpeg = MagicMock()
    ffmpeg.get_media_info_sync.return_value = _media_info()

    file_service = MagicMock()
    file_info = MagicMock(
        file_path=tmp_path / "v.mp4",
        original_filename="v.mp4",
    )
    file_service.get_file.return_value = file_info
    file_service.require_file.return_value = file_info
    file_service.upload_dir = tmp_path / "upload"
    file_service.upload_dir.mkdir()
    file_service.output_dir = tmp_path / "out"
    file_service.output_dir.mkdir()

    def _register_output(file_id, file_path, original_filename):
        return MagicMock(filename=file_path.name, file_size=file_path.stat().st_size)
    file_service.register_output.side_effect = _register_output

    task_manager = MagicMock()
    chat_service = MagicMock()
    # Default mock returns hierarchical-markdown for bullets mode
    chat_service.chat.return_value = (
        "## 主題\n"
        "- **第一段：** 介紹內容 [00:00-00:05]\n"
        "- **第二段：** 後續內容 [00:05-00:10]\n"
    )

    svc = VideoSummaryService(
        ffmpeg=ffmpeg,
        file_service=file_service,
        task_manager=task_manager,
        chat_service=chat_service,
        model_manager=MagicMock(),
        whisper=MagicMock(),
        demucs=MagicMock(),
        alignment_engine=MagicMock(),
    )
    return svc, file_service


def test_execute_produces_zip_with_md_and_frames(tmp_path):
    svc, file_service = _make_svc_with_mocks(tmp_path)

    class FakeDetector:
        def __init__(self, *a, **kw):
            pass

        def detect_in_window(self, *a, **kw):
            return []

        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-jpg")

    fake_result = MagicMock(
        segments=[
            MagicMock(start=0.0, end=5.0, text="這是第一段測試"),
            MagicMock(start=5.0, end=10.0, text="這是第二段內容"),
        ],
        language="zh",
    )

    progress_events: list[tuple[float, str]] = []

    def on_progress(p, m):
        progress_events.append((p, m))

    with patch("app.services.video.summary_service.service.transcribe_audio_sync", return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector", FakeDetector):
        result = svc._execute(
            params={
                "file_id": "f1",
                "llm_model_family": "qwen3.5",
                "llm_model_size": "9b",
                "language": "zh-TW",
                "vlm_model_family": None,
                "vlm_model_size": None,
                "summary_mode": "bullets",
            },
            progress_callback=on_progress,
        )

    assert "output_file_id" in result
    assert result["bullet_count"] == 2
    assert result["turning_point_count"] == 0
    assert progress_events[-1] == (1.0, "task.progress.summary_complete")
    zips = list(file_service.output_dir.glob("*_summary_*.zip"))
    assert len(zips) == 1


# ── fix/video-summary-frame-ts-clamp: per-item resilience ──────────────
def _run_execute(svc, detector_cls):
    fake_result = MagicMock(
        segments=[
            MagicMock(start=0.0, end=5.0, text="這是第一段測試"),
            MagicMock(start=5.0, end=10.0, text="這是第二段內容"),
        ],
        language="zh",
    )
    events: list[tuple[float, str]] = []
    with patch("app.services.video.summary_service.service.transcribe_audio_sync", return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector", detector_cls):
        return svc._execute(
            params={
                "file_id": "f1",
                "llm_model_family": "qwen3.5",
                "llm_model_size": "9b",
                "language": "zh-TW",
                "vlm_model_family": None,
                "vlm_model_size": None,
                "summary_mode": "bullets",
            },
            progress_callback=lambda p, m: events.append((p, m)),
        ), events


def test_execute_tolerates_failing_frame(tmp_path):
    svc, file_service = _make_svc_with_mocks(tmp_path)

    class FlakyDetector:
        calls = 0

        def __init__(self, *a, **kw):
            pass

        def detect_in_window(self, *a, **kw):
            return []

        def extract_frame(self, input_path, output_path, timestamp):
            FlakyDetector.calls += 1
            if FlakyDetector.calls == 2:  # 2nd bullet's frame fails
                raise RuntimeError("Frame extraction failed: simulated")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-jpg")

    result, events = _run_execute(svc, FlakyDetector)

    # Task still completes despite one frame failing.
    assert "output_file_id" in result
    assert result["bullet_count"] == 2  # from merged.bullet_items, not frames
    assert events[-1] == (1.0, "task.progress.summary_complete")
    zips = list(file_service.output_dir.glob("*_summary_*.zip"))
    assert len(zips) == 1
    # Only the first bullet's frame made it into the zip (work_dir is
    # rmtree'd in finally, so inspect the archive, not the staging dir).
    import zipfile
    with zipfile.ZipFile(zips[0]) as zf:
        jpgs = [n for n in zf.namelist() if n.endswith(".jpg")]
    assert len(jpgs) == 1


def test_execute_all_frames_fail_still_produces_zip(tmp_path):
    svc, file_service = _make_svc_with_mocks(tmp_path)

    class DeadDetector:
        def __init__(self, *a, **kw):
            pass

        def detect_in_window(self, *a, **kw):
            return []

        def extract_frame(self, input_path, output_path, timestamp):
            raise RuntimeError("Frame extraction failed: simulated total failure")

    result, events = _run_execute(svc, DeadDetector)

    # No raise even when every frame fails; image-less report still produced.
    assert "output_file_id" in result
    assert result["bullet_count"] == 2
    assert events[-1] == (1.0, "task.progress.summary_complete")
    zips = list(file_service.output_dir.glob("*_summary_*.zip"))
    assert len(zips) == 1
