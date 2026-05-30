"""video_download schema defaults + coercion."""
from app.schemas.video_download import (
    VideoDownloadSettings, FormatIntent, ProbeResponse,
)


def test_settings_defaults_are_fail_closed():
    s = VideoDownloadSettings()
    assert s.agreed is False
    assert s.enabled is False
    assert s.quality_mode == "auto"
    assert s.max_height == 1080


def test_settings_partial_validate_fills_defaults():
    s = VideoDownloadSettings.model_validate({"enabled": True, "agreed": True})
    assert s.enabled is True and s.quality_mode == "auto"


def test_format_intent_defaults_to_auto():
    assert FormatIntent().mode == "auto"


def test_probe_response_coerces_format_dicts():
    r = ProbeResponse(downloadable=True, formats=[
        {"format_id": "137", "height": 1080, "ext": "mp4", "note": "1080p"},
    ])
    assert r.formats[0].format_id == "137"
    assert r.formats[0].height == 1080
