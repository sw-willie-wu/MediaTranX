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
    # Default mock returns hierarchical-markdown for bullets mode. The mock
    # transcribe (fake_result) supplies 2 segments → cites reference lines L1/L2.
    chat_service.chat.return_value = (
        "## 主題\n"
        "- **第一段：** 介紹內容 [L1-L1]\n"
        "- **第二段：** 後續內容 [L2-L2]\n"
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
    svc._chat_service.chat.return_value = (
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
    svc._chat_service.chat.return_value = (
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
    svc._chat_service.chat.return_value = "唯一一段敘事。 [L1-L2]\n"
    # VLM rejects every candidate.
    svc._chat_service.chat_with_images = MagicMock(return_value="-1")

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
    chat_service.chat.return_value = chat_markdown
    svc = VideoSummaryService(
        ffmpeg=ffmpeg, file_service=file_service, task_manager=MagicMock(),
        chat_service=chat_service, model_manager=MagicMock(), whisper=MagicMock(),
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
    svc._chat_service.chat_with_images = MagicMock(return_value="0")

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


# ── summary-1.4.1: Bug B — scene detection progress event ─────────────
def test_execute_emits_detecting_scenes_progress_before_frames(tmp_path):
    """Bug B: detect_all() 前發出 summary_detecting_scenes 進度事件,
    且排在第一個 bullet-frame 事件之前 —— 進度條在場景偵測階段不凍住。"""
    svc, file_service = _make_svc_with_mocks(tmp_path)

    class FakeDetector:
        def __init__(self, *a, **kw): pass
        def detect_in_window(self, *a, **kw): return []
        def detect_all(self, *a, **kw): return []
        def extract_frame(self, input_path, output_path, timestamp, max_edge=None):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"j")

    fake_result = MagicMock(
        segments=[MagicMock(start=0.0, end=5.0, text="一"),
                  MagicMock(start=5.0, end=10.0, text="二")],
        language="zh",
    )
    events: list[tuple[float, str]] = []
    with patch("app.services.video.summary_service.service.transcribe_audio_sync",
               return_value=fake_result), \
         patch("app.services.video.summary_service.service.SceneDetector",
               FakeDetector):
        svc._execute(
            params={"file_id": "f1", "llm_model_family": "qwen3.5",
                    "llm_model_size": "9b", "language": "zh-TW",
                    "vlm_model_family": None, "vlm_model_size": None,
                    "summary_mode": "bullets"},
            progress_callback=lambda p, m: events.append((p, m)),
        )

    msgs = [m for _, m in events]
    detect_evts = [i for i, m in enumerate(msgs)
                   if m == "task.progress.summary_detecting_scenes"]
    frame_evts = [i for i, m in enumerate(msgs)
                  if m.startswith("task.progress.summary_bullet_frame")]
    assert detect_evts, "expected a summary_detecting_scenes progress event"
    assert frame_evts, "expected at least one bullet-frame progress event"
    # ordering only — do NOT assert the literal pct value
    assert detect_evts[0] < frame_evts[0]
