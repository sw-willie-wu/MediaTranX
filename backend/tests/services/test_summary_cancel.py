"""TaskCancelledError must escape the nested summary swallow shapes."""
import pytest
from app.handler.exceptions import TaskCancelledError


def test_frame_picker_reraises_taskcancelled(tmp_path):
    """pick_frame_timestamp's vlm try/except must NOT swallow TaskCancelledError."""
    from app.services.video.summary_service import frame_picker

    detector = type("D", (), {"extract_frame": staticmethod(lambda **k: None)})()

    def vlm_cb(ctx, paths):
        raise TaskCancelledError("cancel")

    with pytest.raises(TaskCancelledError):
        frame_picker.pick_frame_timestamp(
            detector=detector, vlm_callback=vlm_cb, video_path=tmp_path / "v.mp4",
            window_start=0.0, window_end=10.0, context_text="t",
            temp_dir=tmp_path / "c", duration=100.0, fps=30.0,
            scenes=[1.0, 2.0, 3.0],  # ≥2 candidates → VLM path
        )


def test_bulletloop_shape_reraises():
    """Anchor: `for: try: <call> except TaskCancelledError: raise except Exception: continue`."""
    def body():
        raise TaskCancelledError("c")

    def run():
        for _ in range(3):
            try:
                body()
            except TaskCancelledError:
                raise
            except Exception:
                continue
    with pytest.raises(TaskCancelledError):
        run()


def test_make_vlm_callback_threads_params():
    """_make_vlm_callback must forward cancel_pct/cancel_msg into
    vlm_session.chat_with_images so the VLM call is guarded.

    New signature (Task 10): (vlm_session, vlm_family, vlm_size, *,
    cancel_pct, cancel_msg). on_progress is no longer a parameter —
    the session's _guard already owns it. cancel_pct/cancel_msg are
    forwarded as per-call overrides to chat_with_images().
    """
    from app.services.video.summary_service.service import VideoSummaryService
    from unittest.mock import MagicMock
    captured = {}

    class FakeSession:
        def chat_with_images(self, **kw):
            captured.update(kw)
            return "0"

    svc = VideoSummaryService.__new__(VideoSummaryService)
    fake_session = FakeSession()
    vlm = svc._make_vlm_callback(
        fake_session, "qwen3vl", "8b",
        cancel_pct=0.7,
        cancel_msg="task.progress.summary_bullet_frame|1|40",
    )
    vlm("ctx", ["a.jpg", "b.jpg"])
    assert captured["cancel_pct"] == 0.7
    assert captured["cancel_msg"] == "task.progress.summary_bullet_frame|1|40"
    # on_progress is no longer forwarded per-call (session's _guard owns it).
    assert "on_progress" not in captured


def test_chunktext_valueerror_shape_does_not_swallow_cancel():
    """AC#4 'both': chunk loop's `except ValueError: continue` must NOT eat
    TaskCancelledError (raised by the guarded one-shot before the parse)."""
    def one_shot_chat():
        raise TaskCancelledError("c")

    def run():
        for _ in range(3):
            raw = one_shot_chat()           # raises TaskCancelledError
            try:
                int(raw)                    # stand-in for parse_bullets_markdown
            except ValueError:
                continue
    with pytest.raises(TaskCancelledError):
        run()
