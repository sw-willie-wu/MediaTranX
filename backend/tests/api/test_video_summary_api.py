"""Video summary API request validation tests."""
import pytest


def test_video_summary_request_accepts_remote_fields():
    """VideoSummaryRequest accepts the new 8 remote fields + 2 Optional locals."""
    from app.api.routes.video.summary import VideoSummaryRequest

    req = VideoSummaryRequest(
        file_id="f1",
        llm_remote=True,
        llm_provider="ollama",
        llm_conn_id=1,
        llm_remote_model="qwen3.5:9b",
        vlm_remote=True,
        vlm_provider="ollama",
        vlm_conn_id=1,
        vlm_remote_model="qwen3vl:8b",
        # llm_model_family / _size unset — that's OK now
    )
    assert req.llm_remote is True
    assert req.llm_model_family is None
    assert req.vlm_remote_model == "qwen3vl:8b"


def test_video_summary_request_accepts_local_only():
    """Pre-spec behaviour preserved: local-only request still works."""
    from app.api.routes.video.summary import VideoSummaryRequest

    req = VideoSummaryRequest(
        file_id="f1",
        llm_model_family="gemma4",
        llm_model_size="4b",
    )
    assert req.llm_remote is False
    assert req.llm_provider is None
    assert req.vlm_remote is False
