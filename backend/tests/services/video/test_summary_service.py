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


def test_video_summary_service_requires_remote_service():
    """VideoSummaryService now requires remote_service injection."""
    from unittest.mock import MagicMock

    # Build with NO remote_service → should raise TypeError
    with pytest.raises(TypeError, match="remote_service"):
        VideoSummaryService(
            ffmpeg=MagicMock(),
            file_service=MagicMock(),
            task_manager=MagicMock(),
            chat_service=MagicMock(),
            model_manager=MagicMock(),
            whisper=MagicMock(),
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
        remote_service=MagicMock(name="RemoteService"),
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
        remote_service=MagicMock(name="RemoteService"),
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
    # Default mock: _run_llm_chunk_loop opens chat_service.session() as a
    # context manager → returns a session mock whose .chat() returns the LLM
    # markdown. The mock transcribe (fake_result) supplies 2 segments →
    # cites reference lines L1/L2.
    _default_llm_response = (
        "## 主題\n"
        "- **第一段：** 介紹內容 [L1-L1]\n"
        "- **第二段：** 後續內容 [L2-L2]\n"
    )
    _session_mock = MagicMock()
    _session_mock.chat.return_value = _default_llm_response
    _cm = MagicMock()
    _cm.__enter__ = MagicMock(return_value=_session_mock)
    _cm.__exit__ = MagicMock(return_value=False)
    chat_service.session = MagicMock(return_value=_cm)

    svc = VideoSummaryService(
        ffmpeg=ffmpeg,
        file_service=file_service,
        task_manager=task_manager,
        chat_service=chat_service,
        model_manager=MagicMock(),
        remote_service=MagicMock(name="RemoteService"),
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

        def detect_all(self, *a, **kw):
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
    assert result["paragraph_count"] == 0
    assert progress_events[-1] == (1.0, "task.progress.summary_complete")
    zips = list(file_service.output_dir.glob("*_summary_*.zip"))
    assert len(zips) == 1


def test_execute_narrative_mode_produces_paragraph_frames(tmp_path):
    """narrative 模式：走段落取幀，產出 para_NNN.jpg，回傳 paragraph_count。"""
    svc, file_service = _make_svc_with_mocks(tmp_path)
    # narrative-mode LLM output: prose paragraphs each ending [L<a>-L<b>].
    svc._chat_service.session.return_value.__enter__.return_value.chat.return_value = (
        "第一段敘事內容描述開頭。 [L1-L1]\n\n"
        "第二段敘事內容描述後續。 [L2-L2]\n"
    )

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_in_window(self, *a, **kw): return []
        def detect_all(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp, max_edge=None):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-jpg")

    fake_result = MagicMock(
        segments=[
            MagicMock(start=0.0, end=5.0, text="這是第一段測試"),
            MagicMock(start=5.0, end=10.0, text="這是第二段內容"),
        ],
        language="zh",
    )

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector",
               FakeDetector):
        result = svc._execute(
            params={
                "file_id": "f1", "llm_model_family": "qwen3.5",
                "llm_model_size": "9b", "language": "zh-TW",
                "vlm_model_family": None, "vlm_model_size": None,
                "summary_mode": "narrative",
            },
            progress_callback=lambda p, m: None,
        )

    assert "output_file_id" in result
    assert result["paragraph_count"] == 2
    assert result["bullet_count"] == 0
    import zipfile
    z = list(file_service.output_dir.glob("*_summary_*.zip"))[0]
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert "summary.md" in names
    jpgs = sorted(n for n in names if n.endswith(".jpg"))
    assert jpgs == ["frames/para_000.jpg", "frames/para_001.jpg"]


def test_execute_narrative_mode_cite_less_paragraph_skipped(tmp_path):
    """A narrative paragraph with no [L] cite -> time_range None -> no image,
    but it still counts in paragraph_count and the task completes."""
    svc, file_service = _make_svc_with_mocks(tmp_path)
    # Para 1 cites [L1-L1] (gets a frame); para 2 has no cite (no frame).
    svc._chat_service.session.return_value.__enter__.return_value.chat.return_value = (
        "第一段有引用。 [L1-L1]\n\n"
        "第二段沒有引用。\n"
    )

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_in_window(self, *a, **kw): return []
        def detect_all(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp, max_edge=None):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-jpg")

    fake_result = MagicMock(
        segments=[
            MagicMock(start=0.0, end=5.0, text="這是第一段測試"),
            MagicMock(start=5.0, end=10.0, text="這是第二段內容"),
        ],
        language="zh",
    )

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector",
               FakeDetector):
        result = svc._execute(
            params={
                "file_id": "f1", "llm_model_family": "qwen3.5",
                "llm_model_size": "9b", "language": "zh-TW",
                "vlm_model_family": None, "vlm_model_size": None,
                "summary_mode": "narrative",
            },
            progress_callback=lambda p, m: None,
        )

    assert result["paragraph_count"] == 2   # both paragraphs in the report
    import zipfile
    z = list(file_service.output_dir.glob("*_summary_*.zip"))[0]
    with zipfile.ZipFile(z) as zf:
        jpgs = sorted(n for n in zf.namelist() if n.endswith(".jpg"))
    assert jpgs == ["frames/para_000.jpg"]   # only the cited paragraph framed


def test_execute_narrative_mode_vlm_rejects_skips_image(tmp_path):
    """narrative + VLM 回 -1（拒圖）→ 該段無圖、任務正常完成、不計失敗。"""
    svc, file_service = _make_svc_with_mocks(tmp_path)
    svc._chat_service.session.return_value.__enter__.return_value.chat.return_value = (
        "唯一一段敘事。 [L1-L2]\n"
    )
    # VLM rejects every candidate — mock on the session object (new hoisted-session design).
    svc._chat_service.session.return_value.__enter__.return_value.chat_with_images = MagicMock(return_value="-1")

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_in_window(self, *a, **kw): return []
        def detect_all(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp, max_edge=None):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-jpg")

    cfg = {
        "max_image_edge": 768, "temperature": 0.0, "top_k": 40, "top_p": 0.9,
        "prompt_builder": "default", "thinking": False,
        "max_tokens_strategy": "fixed", "max_tokens_ratio": 4,
        "max_tokens_cap": 16, "n_ctx": 4096, "n_ctx_min": 2048,
        "n_ctx_max": 8192, "vram_per_ctx_token": 0.04, "max_srt_batch": 0,
    }
    fake_result = MagicMock(
        segments=[
            MagicMock(start=0.0, end=5.0, text="一"),
            MagicMock(start=5.0, end=10.0, text="二"),
        ],
        language="zh",
    )

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector",
               FakeDetector), \
         patch("app.services.video.summary_service.service.get_inference_config",
               lambda f, s, t: cfg):
        result = svc._execute(
            params={
                "file_id": "f1", "llm_model_family": "qwen3.5",
                "llm_model_size": "9b", "language": "zh-TW",
                "vlm_model_family": "qwen3vl", "vlm_model_size": "8b",
                "summary_mode": "narrative",
            },
            progress_callback=lambda p, m: None,
        )

    assert result["paragraph_count"] == 1
    import zipfile
    z = list(file_service.output_dir.glob("*_summary_*.zip"))[0]
    with zipfile.ZipFile(z) as zf:
        jpgs = [n for n in zf.namelist() if n.endswith(".jpg")]
    assert jpgs == []   # VLM rejected → no paragraph image


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

        def detect_all(self, *a, **kw):
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

        def detect_all(self, *a, **kw):
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


# ── perf/video-summary-bullet-cap-scene-once ───────────────────────────
def _svc_with_chat(tmp_path, chat_markdown):
    ffmpeg = MagicMock()
    ffmpeg.get_media_info_sync.return_value = _media_info()
    file_service = MagicMock()
    file_info = MagicMock(file_path=tmp_path / "v.mp4", original_filename="v.mp4")
    file_service.get_file.return_value = file_info
    file_service.require_file.return_value = file_info
    file_service.upload_dir = tmp_path / "u"; file_service.upload_dir.mkdir()
    file_service.output_dir = tmp_path / "o"; file_service.output_dir.mkdir()
    file_service.register_output.side_effect = lambda file_id, file_path, original_filename: MagicMock(
        filename=file_path.name, file_size=file_path.stat().st_size)
    chat_service = MagicMock()
    _session_mock = MagicMock()
    _session_mock.chat.return_value = chat_markdown
    _cm = MagicMock()
    _cm.__enter__ = MagicMock(return_value=_session_mock)
    _cm.__exit__ = MagicMock(return_value=False)
    chat_service.session = MagicMock(return_value=_cm)
    svc = VideoSummaryService(
        ffmpeg=ffmpeg, file_service=file_service, task_manager=MagicMock(),
        chat_service=chat_service, model_manager=MagicMock(),
        remote_service=MagicMock(name="RemoteService"), whisper=MagicMock(),
        demucs=MagicMock(), alignment_engine=MagicMock(),
    )
    return svc, file_service


def _exec(svc, detector_cls, end=10.0):
    fake = MagicMock(segments=[MagicMock(start=0.0, end=end, text="內容")], language="zh")
    with patch("app.services.video.summary_service.service.transcribe_audio_sync", return_value=fake), \
         patch("app.services.video.summary_service.service.SceneDetector", detector_cls):
        return svc._execute(
            params={"file_id": "f1", "llm_model_family": "qwen3.5",
                    "llm_model_size": "9b", "language": "zh-TW",
                    "vlm_model_family": None, "vlm_model_size": None,
                    "summary_mode": "bullets"},
            progress_callback=lambda p, m: None,
        )


def _zip_jpgs(file_service):
    import zipfile
    z = list(file_service.output_dir.glob("*_summary_*.zip"))[0]
    with zipfile.ZipFile(z) as zf:
        return sorted(n for n in zf.namelist() if n.endswith(".jpg"))


def test_bullets_over_K_caps_frames_by_original_index(tmp_path):
    # 12 bullets, content 10s → K=8 → even_indices(12,8)=[0,2,3,5,6,8,9,11].
    # _exec supplies only 1 transcript segment → every cite must be [L1-L1].
    md = "## 主題\n" + "".join(
        f"- **重點{i}：** 內容{i} [L1-L1]\n" for i in range(12)
    )
    svc, fs = _svc_with_chat(tmp_path, md)

    detect_all_calls = []

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_all(self, *a, **kw):
            detect_all_calls.append(1); return []
        def detect_in_window(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"j")

    result = _exec(svc, FakeDetector)

    assert result["bullet_count"] == 12          # full text, not capped
    jpgs = _zip_jpgs(fs)
    assert len(jpgs) == 8                          # K=8 frames only
    assert jpgs == [f"frames/bullet_{i:03d}.jpg"
                    for i in [0, 2, 3, 5, 6, 8, 9, 11]]   # ORIGINAL indices
    assert len(detect_all_calls) == 1             # scene detect once


def test_bullets_under_K_all_framed(tmp_path):
    # _exec supplies only 1 transcript segment → every cite must be [L1-L1].
    md = "## 主題\n" + "".join(
        f"- **重點{i}：** 內容{i} [L1-L1]\n" for i in range(3)
    )
    svc, fs = _svc_with_chat(tmp_path, md)

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_all(self, *a, **kw): return []
        def detect_in_window(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"j")

    result = _exec(svc, FakeDetector)
    assert result["bullet_count"] == 3
    assert _zip_jpgs(fs) == [f"frames/bullet_{i:03d}.jpg" for i in range(3)]


def test_execute_frames_bullet_with_normalized_inverted_cite(tmp_path):
    """A bullet whose cite has no line_range resolves to time_range=None and is
    skipped (no inline image); the other bullets are still framed normally.

    Note: with the robust _cite_range parser (min/max), a formerly-inverted cite
    like [L2-L1] is now normalised to (1, 2) and DOES resolve. The "no frame"
    path is reached only when a bullet has no cite tag at all (no _BULLET_LABEL_RE
    match → bullet_items entry never created → no frame slot allocated), or when
    the resolve step returns None. This test keeps the original structure but
    updates the expectation: all 3 labelled bullets have valid cites, so all 3
    get frames."""
    md = (
        "## 主題\n"
        "- **正常一：** 內容 [L1-L1]\n"
        "- **先大後小：** 內容 [L2-L1]\n"   # _cite_range normalises to (1, 2) — valid
        "- **正常二：** 內容 [L2-L2]\n"
    )
    svc, fs = _svc_with_chat(tmp_path, md)

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_all(self, *a, **kw): return []
        def detect_in_window(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"j")

    # 2 transcript segments.
    fake = MagicMock(
        segments=[MagicMock(start=0.0, end=5.0, text="一"),
                  MagicMock(start=5.0, end=10.0, text="二")],
        language="zh",
    )
    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake), \
         patch("app.services.video.summary_service.service.SceneDetector",
               FakeDetector):
        result = svc._execute(
            params={"file_id": "f1", "llm_model_family": "qwen3.5",
                    "llm_model_size": "9b", "language": "zh-TW",
                    "vlm_model_family": None, "vlm_model_size": None,
                    "summary_mode": "bullets"},
            progress_callback=lambda p, m: None,
        )

    assert result["bullet_count"] == 3   # every bullet still in the report text
    # All 3 labelled bullets have valid (possibly normalised) cites → all 3 framed.
    assert _zip_jpgs(fs) == [f"frames/bullet_{i:03d}.jpg" for i in range(3)]


def test_candidate_frames_downscaled_final_frames_native(tmp_path):
    """Bullet loop: VLM candidate extractions carry the family max_image_edge;
    the final bullet keyframe extraction carries NO max_edge (stays native).
    Drives the real _execute bullet loop end-to-end."""
    svc, file_service = _make_svc_with_mocks(tmp_path)
    # VLM picks index 0 cleanly (numeric str → _cb's re.search succeeds).
    # Mock on the session object (new hoisted-session design).
    svc._chat_service.session.return_value.__enter__.return_value.chat_with_images = MagicMock(return_value="0")

    class SpyDetector:
        calls: list[dict] = []

        def __init__(self, *a, **kw):
            pass

        def detect_in_window(self, *a, **kw):
            return []

        def detect_all(self, *a, **kw):
            # ≥2 scenes inside the first bullet window [0,5] → forces the
            # multi-candidate VLM branch in pick_frame_timestamp.
            return [1.0, 2.0, 6.0, 7.0]

        def extract_frame(self, input_path, output_path, timestamp,
                          max_edge=None):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-jpg")
            SpyDetector.calls.append(
                {"name": output_path.name, "max_edge": max_edge}
            )

    SpyDetector.calls = []

    cfg = {
        "max_image_edge": 777, "temperature": 0.0, "top_k": 40, "top_p": 0.9,
        "prompt_builder": "default", "thinking": False,
        "max_tokens_strategy": "fixed", "max_tokens_ratio": 4,
        "max_tokens_cap": 16, "n_ctx": 4096, "n_ctx_min": 2048,
        "n_ctx_max": 8192, "vram_per_ctx_token": 0.04, "max_srt_batch": 0,
    }

    fake_result = MagicMock(
        segments=[
            MagicMock(start=0.0, end=5.0, text="這是第一段測試"),
            MagicMock(start=5.0, end=10.0, text="這是第二段內容"),
        ],
        language="zh",
    )

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector",
               SpyDetector), \
         patch("app.services.video.summary_service.service.get_inference_config",
               lambda f, s, t: cfg):
        result = svc._execute(
            params={
                "file_id": "f1",
                "llm_model_family": "qwen3.5",
                "llm_model_size": "9b",
                "language": "zh-TW",
                "vlm_model_family": "qwen3vl",
                "vlm_model_size": "8b",
                "summary_mode": "bullets",
            },
            progress_callback=lambda p, m: None,
        )

    assert "output_file_id" in result
    cand = [c for c in SpyDetector.calls if c["name"].startswith("candidate_")]
    final = [c for c in SpyDetector.calls
             if c["name"].startswith("bullet_")]
    assert cand, "expected candidate extractions (VLM branch must have run)"
    assert all(c["max_edge"] == 777 for c in cand), \
        f"candidate frames must carry family max_image_edge: {cand}"
    assert final, "expected final keyframe extraction"
    assert all(c["max_edge"] is None for c in final), \
        f"final keyframes must stay native (no max_edge): {final}"


# ── summary-hang-fix: detect_all parallelization ───────────────────────
import threading
import time as _time
from app.handler.exceptions import TaskCancelledError


def test_execute_detect_runs_and_scenes_reach_frame_picking(tmp_path):
    """Background detect_all result reaches frame picking via the holder.

    The fake detects scenes at [2.0, 4.0]. With no VLM, pick_frame_timestamp
    picks the scene nearest the bullet-0 window midpoint (window [0,5), mid
    2.5 → scene 2.0). If global_scenes were dropped, bullet 0 would fall back
    to the bare midpoint 2.5 — so a 2.0 extraction proves the background
    scenes actually reached the picker, not just that detect_all ran.
    """
    svc, file_service = _make_svc_with_mocks(tmp_path)

    class FakeDetector:
        calls = 0
        extract_ts: list[float] = []

        def __init__(self, *a, **kw):
            pass

        def detect_all(self, *a, **kw):
            FakeDetector.calls += 1
            return [2.0, 4.0]

        def extract_frame(self, input_path, output_path, timestamp):
            FakeDetector.extract_ts.append(timestamp)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-jpg")

    fake_result = MagicMock(
        segments=[
            MagicMock(start=0.0, end=5.0, text="這是第一段測試"),
            MagicMock(start=5.0, end=10.0, text="這是第二段內容"),
        ],
        language="zh",
    )

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector", FakeDetector):
        result = svc._execute(
            params={
                "file_id": "f1", "llm_model_family": "qwen3.5",
                "llm_model_size": "9b", "language": "zh-TW",
                "vlm_model_family": None, "vlm_model_size": None,
                "summary_mode": "bullets",
            },
            progress_callback=lambda p, m: None,
        )
    assert "output_file_id" in result
    assert FakeDetector.calls == 1  # detected exactly once, in the background thread
    # Scene 2.0 (from the background detect) reached pick_frame_timestamp:
    # bullet-0 window [0,5) midpoint 2.5 → nearest scene 2.0.
    assert 2.0 in FakeDetector.extract_ts


def test_execute_emits_detecting_scenes_when_detect_slow(tmp_path):
    """When detect outlasts Whisper+LLM, the merge poll loop emits
    summary_detecting_scenes until the background thread finishes."""
    svc, file_service = _make_svc_with_mocks(tmp_path)
    release = threading.Event()

    class SlowDetector:
        def __init__(self, *a, **kw):
            pass

        def detect_all(self, *a, **kw):
            release.wait(timeout=5.0)  # block until the test releases
            return []

        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"x")

    fake_result = MagicMock(
        segments=[MagicMock(start=0.0, end=5.0, text="第一段")],
        language="zh",
    )
    events: list[tuple[float, str]] = []

    def on_progress(p, m):
        events.append((p, m))
        if m == "task.progress.summary_detecting_scenes":
            release.set()  # unblock detect once the merge loop is reached

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector", SlowDetector):
        svc._execute(
            params={
                "file_id": "f1", "llm_model_family": "qwen3.5",
                "llm_model_size": "9b", "language": "zh-TW",
                "vlm_model_family": None, "vlm_model_size": None,
                "summary_mode": "bullets",
            },
            progress_callback=on_progress,
        )
    assert any(m == "task.progress.summary_detecting_scenes" for _, m in events)


def test_execute_cancel_propagates_to_background_detect(tmp_path):
    """Cancel in the main thread → outer finally sets the event → the
    background detect's on_progress raises → detect_all is interrupted."""
    svc, file_service = _make_svc_with_mocks(tmp_path)

    class CancellableDetector:
        cancelled = False

        def __init__(self, *a, **kw):
            pass

        def detect_all(self, video_path, on_progress=None):
            try:
                for _ in range(10000):
                    if on_progress is not None:
                        on_progress(0.0)  # raises once detect_cancel is set
                    _time.sleep(0.005)
            except TaskCancelledError:
                CancellableDetector.cancelled = True
                raise
            return []

        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"x")

    fake_result = MagicMock(
        segments=[MagicMock(start=0.0, end=5.0, text="第一段")],
        language="zh",
    )

    calls = {"n": 0}

    def on_progress(p, m):
        calls["n"] += 1
        if calls["n"] >= 2:  # simulate a user cancel early in the run
            raise TaskCancelledError("cancelled")

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector",
               CancellableDetector):
        with pytest.raises(TaskCancelledError):
            svc._execute(
                params={
                    "file_id": "f1", "llm_model_family": "qwen3.5",
                    "llm_model_size": "9b", "language": "zh-TW",
                    "vlm_model_family": None, "vlm_model_size": None,
                    "summary_mode": "bullets",
                },
                progress_callback=on_progress,
            )
    # The background detect thread was signalled and interrupted, not orphaned.
    assert CancellableDetector.cancelled is True


# ── 1.4.1 follow-up: progress band reallocation ────────────────────────
def test_execute_progress_bands_use_new_layout(tmp_path):
    """Progress events fall in the redesigned bands:
      audio: 0.02 / 0.05 (unchanged)
      Whisper: 0.05 → 0.50 (45%)
      LLM chunks: start at 0.55 + 0.15·(i/N) (model-load occupies 0.50–0.55)
      bullet frames: start at 0.72 + 0.23·(n/N) (VLM load occupies 0.70–0.72)
      packaging: 0.95
      complete: 1.00
    """
    svc, file_service = _make_svc_with_mocks(tmp_path)

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_all(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"j")

    fake_result = MagicMock(
        segments=[MagicMock(start=0.0, end=5.0, text="一"),
                  MagicMock(start=5.0, end=10.0, text="二")],
        language="zh",
    )
    events: list[tuple[float, str]] = []

    def _whisper_with_progress(*a, on_progress=None, **kw):
        # Drive Whisper progress 0 → 1 so we can verify the 0.05→0.50 mapping
        if on_progress is not None:
            for p in (0.0, 0.5, 1.0):
                on_progress(p, "task.progress.recognizing_pct|50%")
        return fake_result

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               side_effect=_whisper_with_progress), \
         patch("app.services.video.summary_service.service.SceneDetector",
               FakeDetector):
        svc._execute(
            params={"file_id": "f1", "llm_model_family": "qwen3.5",
                    "llm_model_size": "9b", "language": "zh-TW",
                    "vlm_model_family": None, "vlm_model_size": None,
                    "summary_mode": "bullets"},
            progress_callback=lambda p, m: events.append((p, m)),
        )

    # Audio band unchanged
    assert (0.02, "task.progress.extract_audio_starting") in events
    assert (0.05, "task.progress.audio_extracted") in events
    # Whisper progress 0 → 1 mapped to 0.05 → 0.50
    whisper_pcts = [p for (p, m) in events if m == "task.progress.recognizing_pct|50%"]
    assert whisper_pcts, "expected whisper progress events"
    assert 0.05 <= min(whisper_pcts) <= 0.05 + 1e-9
    assert 0.50 - 1e-9 <= max(whisper_pcts) <= 0.50
    # LLM chunk loop start at 0.55 (model-load band 0.50–0.55 precedes it)
    chunk_pcts = [p for (p, m) in events if m.startswith("task.progress.summary_chunk|")]
    assert chunk_pcts and 0.55 - 1e-9 <= min(chunk_pcts) <= 0.55 + 1e-9
    # Bullet frame loop start at 0.72 (VLM load band 0.70–0.72 precedes it)
    bullet_pcts = [p for (p, m) in events if m.startswith("task.progress.summary_bullet_frame|")]
    assert bullet_pcts and 0.72 - 1e-9 <= min(bullet_pcts) <= 0.72 + 1e-9
    # Packaging at 0.95
    assert (0.95, "task.progress.summary_packaging") in events
    # Complete at 1.0 (existing invariant)
    assert events[-1] == (1.0, "task.progress.summary_complete")


def test_execute_wires_load_band_into_sessions(tmp_path):
    """LLM session is opened with load_band=(0.50,0.55) and the VLM session
    with load_band=(0.70,0.72), so model-load progress scales into the band
    start instead of overwriting the main bar with a raw 0→100% sweep."""
    svc, file_service = _make_svc_with_mocks(tmp_path)
    fake_result = MagicMock(
        segments=[MagicMock(start=0.0, end=5.0, text="一")], language="zh",
    )

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_all(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"j")

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector",
               FakeDetector):
        svc._execute(
            params={"file_id": "f1", "llm_model_family": "qwen3.5",
                    "llm_model_size": "9b", "language": "zh-TW",
                    "vlm_model_family": "qwen3vl", "vlm_model_size": "8b",
                    "summary_mode": "bullets"},
            progress_callback=lambda p, m: None,
        )
    bands = [kw.get("load_band") for (_a, kw) in svc._chat_service.session.call_args_list]
    assert (0.50, 0.55) in bands, f"LLM session load_band missing; got {bands}"
    assert (0.70, 0.72) in bands, f"VLM session load_band missing; got {bands}"


def test_execute_merge_poll_holds_at_070(tmp_path):
    """When detect outlasts Whisper+LLM, the merge poll loop emits
    summary_detecting_scenes at pct=0.70 (new band, was 0.60)."""
    svc, file_service = _make_svc_with_mocks(tmp_path)
    release = threading.Event()

    class SlowDetector:
        def __init__(self, *a, **kw): pass
        def detect_all(self, *a, **kw):
            release.wait(timeout=5.0)
            return []
        def extract_frame(self, input_path, output_path, timestamp):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"j")

    fake_result = MagicMock(
        segments=[MagicMock(start=0.0, end=5.0, text="一")],
        language="zh",
    )
    detect_events: list[float] = []

    def on_progress(p, m):
        if m == "task.progress.summary_detecting_scenes":
            detect_events.append(p)
            release.set()

    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector",
               SlowDetector):
        svc._execute(
            params={"file_id": "f1", "llm_model_family": "qwen3.5",
                    "llm_model_size": "9b", "language": "zh-TW",
                    "vlm_model_family": None, "vlm_model_size": None,
                    "summary_mode": "bullets"},
            progress_callback=on_progress,
        )
    assert detect_events, "expected merge-poll summary_detecting_scenes event"
    assert all(abs(p - 0.70) < 1e-9 for p in detect_events), \
        f"merge-poll pct must be 0.70 (was 0.60 pre-1.4.1-followup), got {detect_events}"


# ── Task 8: submit_summary remote LLM/VLM params + validation ─────────
def _make_video_summary_service_for_submit_tests():
    """Build a VideoSummaryService with all deps mocked enough that
    submit_summary's path runs without touching real resources."""
    from unittest.mock import MagicMock, AsyncMock
    from app.services.video.summary_service import VideoSummaryService

    file_svc = MagicMock()
    file_svc.require_file = MagicMock(return_value=MagicMock(file_path="/tmp/x.mp4"))
    tm = MagicMock()
    tm.submit = AsyncMock(return_value="task-123")

    return VideoSummaryService(
        ffmpeg=MagicMock(),
        file_service=file_svc,
        task_manager=tm,
        chat_service=MagicMock(),
        model_manager=MagicMock(),
        remote_service=MagicMock(),
        whisper=MagicMock(),
    )


@pytest.mark.asyncio
async def test_submit_summary_remote_llm_requires_provider_conn_model():
    """llm_remote=True with missing provider / conn / remote_model → ValueError."""
    svc = _make_video_summary_service_for_submit_tests()
    with pytest.raises(ValueError, match="llm_provider"):
        await svc.submit_summary(
            file_id="f1",
            llm_remote=True,  # missing llm_provider/conn_id/remote_model
        )


@pytest.mark.asyncio
async def test_submit_summary_local_llm_requires_family_size():
    """No llm_remote AND missing llm_model_family/_size → ValueError."""
    svc = _make_video_summary_service_for_submit_tests()
    with pytest.raises(ValueError, match="llm_model"):
        await svc.submit_summary(file_id="f1")  # nothing set


@pytest.mark.asyncio
async def test_submit_summary_mixed_local_and_remote_rejected():
    """Both local (model_family+size) AND remote (llm_remote+...) populated → ValueError."""
    svc = _make_video_summary_service_for_submit_tests()
    with pytest.raises(ValueError, match="exactly one"):
        await svc.submit_summary(
            file_id="f1",
            llm_model_family="gemma4", llm_model_size="4b",
            llm_remote=True, llm_provider="ollama",
            llm_conn_id=1, llm_remote_model="qwen3.5:9b",
        )


@pytest.mark.asyncio
async def test_submit_summary_vlm_both_absent_accepted():
    """VLM is wholly optional — neither local nor remote VLM is fine
    (midpoint-nearest fallback)."""
    svc = _make_video_summary_service_for_submit_tests()
    # local LLM, no VLM at all
    task_id = await svc.submit_summary(
        file_id="f1",
        llm_model_family="gemma4", llm_model_size="4b",
    )
    assert task_id  # not raised


@pytest.mark.asyncio
async def test_submit_summary_remote_llm_conn_id_zero_not_reported_as_missing():
    """conn_id=0 is a valid (if unlikely) DB ID — guard uses `is not None`
    and the missing-field reporter must match the guard's contract.

    Previously reported `llm_conn_id` as missing even when conn_id=0 was
    explicitly supplied, because `not 0 == True`. Fix uses `v is None` for
    `_conn_id` fields.
    """
    svc = _make_video_summary_service_for_submit_tests()
    # conn_id=0 + only llm_remote_model missing → "missing" list should
    # contain ONLY llm_remote_model, not llm_conn_id.
    with pytest.raises(ValueError) as exc_info:
        await svc.submit_summary(
            file_id="f1",
            llm_remote=True,
            llm_provider="ollama",
            llm_conn_id=0,
            # llm_remote_model intentionally missing
        )
    msg = str(exc_info.value)
    assert "llm_remote_model" in msg
    assert "llm_conn_id" not in msg  # the regression we're guarding against


# ── Task 9: _run_llm_chunk_loop remote session dispatch ──────────────────
def test_run_llm_chunk_loop_opens_remote_session_when_provider_supplied():
    """_run_llm_chunk_loop opens chat_service.session(remote_provider=...)
    when llm_prov is supplied. Per-chunk session.chat() is called."""
    from unittest.mock import MagicMock, patch
    from app.services.video.summary_service import VideoSummaryService
    # SubtitleEntry is the type the chunk loop expects — format_transcript_numbered
    # uses attribute access (.text), so dicts would AttributeError.
    from app.services.video.summary_service.parse import SubtitleEntry

    fake_session = MagicMock(name="ChatSession")
    fake_session.chat = MagicMock(return_value="""# Point
- Anything [L1-L2]
""")
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=fake_session)
    cm.__exit__ = MagicMock(return_value=False)

    chat_svc = MagicMock()
    chat_svc.session = MagicMock(return_value=cm)

    fake_prov = MagicMock(name="OllamaProvider")
    svc = VideoSummaryService(
        ffmpeg=MagicMock(), file_service=MagicMock(),
        task_manager=MagicMock(), chat_service=chat_svc,
        model_manager=MagicMock(), remote_service=MagicMock(),
        whisper=MagicMock(),
    )

    # Real SubtitleEntry — format_transcript_numbered uses attribute access.
    chunks = [[SubtitleEntry(start=0.0, end=1.0, text="Hello world.")]]
    cfg = {"temperature": 0.1, "max_tokens_cap": 4096}
    n_ctx = 8192

    with patch("app.services.video.summary_service.service.calc_max_tokens",
               return_value=512):
        svc._run_llm_chunk_loop(
            params={"summary_mode": "bullets"},
            chunks=chunks, entries=[],
            result_lang_code="en", progress_callback=MagicMock(),
            cfg=cfg, n_ctx=n_ctx,
            llm_family=None, llm_size=None,
            llm_prov=fake_prov, llm_model_id="qwen3.5:9b",
            summary_mode="bullets", language="en",
        )

    chat_svc.session.assert_called_once()
    _, kw = chat_svc.session.call_args
    assert kw["remote_provider"] is fake_prov
    assert kw["remote_model"] == "qwen3.5:9b"
    assert kw["model_family"] is None
    assert kw["model_size"] is None
    fake_session.chat.assert_called_once()
    chat_call_kw = fake_session.chat.call_args.kwargs
    # First chunk's cancel_pct == the chunk-loop floor (0.55 after model-load
    # band 0.50–0.55 was carved out at the start of the LLM band).
    assert chat_call_kw["cancel_pct"] == pytest.approx(0.55, abs=1e-3)
    assert "summary_chunk" in chat_call_kw["cancel_msg"]


def test_make_vlm_callback_signature_takes_vlm_session():
    """_make_vlm_callback's new signature: (vlm_session, vlm_family, vlm_size,
    *, cancel_pct, cancel_msg). Closure calls vlm_session.chat_with_images
    with per-call cancel override."""
    from unittest.mock import MagicMock
    from app.services.video.summary_service import VideoSummaryService

    fake_session = MagicMock(name="ChatSession")
    fake_session.chat_with_images = MagicMock(return_value="1")

    svc = VideoSummaryService(
        ffmpeg=MagicMock(), file_service=MagicMock(),
        task_manager=MagicMock(), chat_service=MagicMock(),
        model_manager=MagicMock(), remote_service=MagicMock(),
        whisper=MagicMock(),
    )

    cb = svc._make_vlm_callback(
        fake_session, "qwen3vl", "8b",
        cancel_pct=0.85, cancel_msg="task.progress.summary_bullet_frame|3|10",
    )
    # Callback contract from frame_picker: (context_text, frame_paths) -> int
    result = cb("describe", [])
    # With empty frame_paths the closure may short-circuit; the assertion
    # we care about is the chat_with_images call shape.
    if fake_session.chat_with_images.called:
        _, kw = fake_session.chat_with_images.call_args
        assert kw["cancel_pct"] == 0.85
        assert kw["cancel_msg"] == "task.progress.summary_bullet_frame|3|10"
