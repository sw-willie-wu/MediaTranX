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


def test_pick_frame_timestamp_forwards_candidate_max_edge(tmp_path):
    """candidate_max_edge reaches the candidate extract call; default None."""
    from unittest.mock import MagicMock
    from pathlib import Path
    from app.services.video.summary_service import frame_picker

    detector = MagicMock()
    detector.extract_frame = MagicMock()
    # Force the multi-candidate VLM branch: 2 scenes in-window.
    vlm_cb = MagicMock(return_value=0)

    frame_picker.pick_frame_timestamp(
        detector=detector,
        vlm_callback=vlm_cb,
        video_path=Path("v.mp4"),
        window_start=0.0,
        window_end=10.0,
        context_text="ctx",
        temp_dir=tmp_path,
        scenes=[1.0, 5.0],
        candidate_max_edge=768,
    )
    for call in detector.extract_frame.call_args_list:
        assert call.kwargs.get("max_edge") == 768

    detector.extract_frame.reset_mock()
    frame_picker.pick_frame_timestamp(
        detector=detector,
        vlm_callback=vlm_cb,
        video_path=Path("v.mp4"),
        window_start=0.0,
        window_end=10.0,
        context_text="ctx",
        temp_dir=tmp_path,
        scenes=[1.0, 5.0],
    )
    for call in detector.extract_frame.call_args_list:
        assert "max_edge" not in call.kwargs  # default → not forwarded


# ── narrative-summary-redesign: VLM image-text gate ────────────────────
def test_pick_returns_none_when_vlm_rejects_all(tmp_path):
    """VLM 回 -1 表全部候選都不符 → pick_frame_timestamp 回 None。"""
    detector = MagicMock()
    detector.detect_in_window.return_value = [12.0, 15.0, 18.0]
    detector.extract_frame = MagicMock()
    vlm = MagicMock(return_value=-1)

    result = pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=10.0, window_end=20.0, context_text="不相符的文字",
        temp_dir=tmp_path,
    )
    assert result is None
    vlm.assert_called_once()


def test_pick_uses_vlm_even_when_no_scenes(tmp_path):
    """有 VLM 時，0 候選也走 VLM（中點當唯一候選）。回 0 → 接受中點。"""
    detector = MagicMock()
    detector.detect_in_window.return_value = []   # 0 candidates
    detector.extract_frame = MagicMock()
    vlm = MagicMock(return_value=0)

    result = pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=10.0, window_end=20.0, context_text="文字",
        temp_dir=tmp_path,
    )
    assert result == 15.0                         # midpoint accepted
    assert detector.extract_frame.call_count == 1  # 1 candidate frame extracted
    vlm.assert_called_once()


def test_pick_uses_vlm_even_when_no_scenes_can_reject(tmp_path):
    """有 VLM、0 候選，VLM 回 -1 → 回 None。"""
    detector = MagicMock()
    detector.detect_in_window.return_value = []
    detector.extract_frame = MagicMock()
    vlm = MagicMock(return_value=-1)

    result = pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=10.0, window_end=20.0, context_text="文字",
        temp_dir=tmp_path,
    )
    assert result is None


def test_pick_vlm_negative_below_minus_one_treated_as_reject(tmp_path):
    """VLM 回 < -1（如 -5）視為拒圖。"""
    detector = MagicMock()
    detector.detect_in_window.return_value = [12.0, 15.0]
    detector.extract_frame = MagicMock()
    vlm = MagicMock(return_value=-5)

    result = pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=10.0, window_end=20.0, context_text="文字",
        temp_dir=tmp_path,
    )
    assert result is None


def test_pick_vlm_skipped_when_temp_dir_missing(tmp_path):
    """有 vlm_callback 但沒 temp_dir → VLM 把關靜默略過，走無-VLM 分支（一定回 float）。"""
    detector = MagicMock()
    detector.detect_in_window.return_value = [12.0, 15.0, 18.0]
    vlm = MagicMock(return_value=-1)   # 即使會拒圖，沒 temp_dir 就不該被呼叫

    result = pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=10.0, window_end=20.0, context_text="文字",
        temp_dir=None,
    )
    assert result == 15.0       # midpoint-nearest, no rejection possible
    vlm.assert_not_called()


# ── narrative-summary-redesign: _make_vlm_callback parsing ─────────────
def _build_cb(chat_return: str):
    """Build a real _make_vlm_callback closure over a fake session.

    Updated for Task 10: new signature is (vlm_session, vlm_family, vlm_size,
    *, cancel_pct, cancel_msg). The session object owns chat_with_images.
    """
    from app.services.video.summary_service.service import VideoSummaryService
    from unittest.mock import patch

    class FakeSession:
        def chat_with_images(self, **kw):
            return chat_return

    svc = VideoSummaryService.__new__(VideoSummaryService)
    # Full inference-config shape so calc_max_tokens inside the closure never
    # KeyErrors regardless of which keys it reads.
    cfg = {
        "max_image_edge": 768, "temperature": 0.0, "top_k": 40, "top_p": 0.9,
        "prompt_builder": "default", "thinking": False,
        "max_tokens_strategy": "fixed", "max_tokens_ratio": 4,
        "max_tokens_cap": 16, "n_ctx": 4096, "n_ctx_min": 2048,
        "n_ctx_max": 8192, "vram_per_ctx_token": 0.04, "max_srt_batch": 0,
    }
    with patch(
        "app.services.video.summary_service.service.get_inference_config",
        lambda f, s, t: cfg,
    ):
        return svc._make_vlm_callback(
            FakeSession(), "qwen3vl", "8b",
            cancel_pct=0.0, cancel_msg="task.progress.summary_bullet_frame|1|1",
        )


def test_vlm_callback_returns_minus_one_on_reject():
    cb = _build_cb("-1")
    assert cb("ctx", ["a.jpg", "b.jpg"]) == -1


def test_vlm_callback_takes_last_number_token():
    """Prompt 文字如「圖片 2 不符，答 -1」→ 取最後一個 token (-1)，不被前面的 2 搶。"""
    cb = _build_cb("圖片 2 不符，答 -1")
    assert cb("ctx", ["a.jpg", "b.jpg", "c.jpg"]) == -1


def test_vlm_callback_plain_index_still_works():
    cb = _build_cb("1")
    assert cb("ctx", ["a.jpg", "b.jpg"]) == 1


def test_vlm_callback_raises_on_no_digits():
    import pytest
    cb = _build_cb("no answer here")
    with pytest.raises(ValueError, match="not a number"):
        cb("ctx", ["a.jpg"])


# ── summary-hang-fix: VLM candidate cap ────────────────────────────────
from app.services.video.summary_service.frame_picker import MAX_VLM_CANDIDATES


def test_pick_vlm_caps_candidates_to_max(tmp_path):
    """VLM path: >MAX candidates → subsampled before extraction + VLM call."""
    detector = MagicMock()
    detector.extract_frame = MagicMock()
    vlm = MagicMock(return_value=0)
    scenes = [float(i) for i in range(1, 21)]  # 20 candidates in [0,100)

    pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=0.0, window_end=100.0, context_text="t",
        temp_dir=tmp_path, scenes=scenes,
    )
    assert MAX_VLM_CANDIDATES == 8
    # 20 candidates capped to 8 → 8 extracts, 8 images to the VLM.
    assert detector.extract_frame.call_count == 8
    ctx, frame_paths = vlm.call_args[0]
    assert len(frame_paths) == 8


def test_pick_vlm_no_cap_when_under_max(tmp_path):
    """VLM path: <=MAX candidates → all kept."""
    detector = MagicMock()
    detector.extract_frame = MagicMock()
    vlm = MagicMock(return_value=0)
    scenes = [1.0, 2.0, 3.0, 4.0, 5.0]  # 5 < 8

    pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=0.0, window_end=100.0, context_text="t",
        temp_dir=tmp_path, scenes=scenes,
    )
    assert detector.extract_frame.call_count == 5
    _, frame_paths = vlm.call_args[0]
    assert len(frame_paths) == 5


def test_pick_vlm_custom_max_candidates(tmp_path):
    """max_candidates param overrides the default cap."""
    detector = MagicMock()
    detector.extract_frame = MagicMock()
    vlm = MagicMock(return_value=0)
    scenes = [float(i) for i in range(1, 21)]

    pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=0.0, window_end=100.0, context_text="t",
        temp_dir=tmp_path, scenes=scenes, max_candidates=4,
    )
    assert detector.extract_frame.call_count == 4


def test_pick_vlm_capped_index_maps_to_sampled_timestamp(tmp_path):
    """VLM idx indexes the SAMPLED list; returned ts is that sampled candidate.

    20 candidates 1.0..20.0; even_indices(20, 8) → [0,3,5,8,11,14,16,19]
    → sampled timestamps [1,4,6,9,12,15,17,20]; idx 2 → 6.0.
    """
    detector = MagicMock()
    detector.extract_frame = MagicMock()
    vlm = MagicMock(return_value=2)
    scenes = [float(i) for i in range(1, 21)]

    result = pick_frame_timestamp(
        detector=detector, vlm_callback=vlm, video_path=Path("x.mp4"),
        window_start=0.0, window_end=100.0, context_text="t",
        temp_dir=tmp_path, scenes=scenes,
    )
    assert result == 6.0


def test_pick_non_vlm_not_capped():
    """Non-VLM path keeps ALL candidates (cheap O(n) min, no cap applied)."""
    detector = MagicMock()
    scenes = [float(i) for i in range(1, 21)]  # 1.0..20.0
    result = pick_frame_timestamp(
        detector=detector, vlm_callback=None, video_path=Path("x.mp4"),
        window_start=0.0, window_end=100.0, context_text="t",
        scenes=scenes,
    )
    # mid = 50.0; nearest of 1..20 → 20.0
    assert result == 20.0
