import pytest
from app.utils.subtitles import (
    Segment,
    format_srt_time, format_vtt_time, format_lrc_time,
    parse_srt_time,
    parse_srt, parse_vtt,
    format_srt, format_vtt, format_txt, format_lrc,
    from_whisper_result,
)


# -- Time formatters --

def test_format_srt_time():
    assert format_srt_time(0.0) == "00:00:00,000"
    assert format_srt_time(1.5) == "00:00:01,500"
    assert format_srt_time(3661.234) == "01:01:01,234"


def test_format_vtt_time_uses_dot():
    assert format_vtt_time(1.5) == "00:00:01.500"


def test_format_lrc_time():
    assert format_lrc_time(0.0) == "[00:00.00]"
    assert format_lrc_time(65.25) == "[01:05.25]"
    assert format_lrc_time(125.5) == "[02:05.50]"


# -- Time parser --

def test_parse_srt_time_handles_comma_and_dot():
    assert parse_srt_time("00:00:01,500") == 1.5
    assert parse_srt_time("00:00:01.500") == 1.5
    assert parse_srt_time("01:01:01,234") == 3661.234


def test_parse_srt_time_rejects_garbage():
    with pytest.raises(ValueError):
        parse_srt_time("not a timestamp")


# -- Parsers --

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,500
第一句

2
00:00:03,500 --> 00:00:06,000
第二句
"""


def test_parse_srt_returns_segments():
    segs = parse_srt(SAMPLE_SRT)
    assert len(segs) == 2
    assert segs[0].start == 1.0
    assert segs[0].end == 3.5
    assert segs[0].text == "第一句"


def test_parse_srt_handles_bom_and_blank_garbage():
    assert parse_srt("") == []
    assert parse_srt("\ufeff" + SAMPLE_SRT) == parse_srt(SAMPLE_SRT)
    assert parse_srt("no index or timestamp here") == []


def test_parse_vtt_ignores_webvtt_header():
    text = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello\n"
    segs = parse_vtt(text)
    assert len(segs) == 1
    assert segs[0].text == "hello"
    assert segs[0].start == 1.0


# -- Formatters --

def test_format_srt_produces_numbered_blocks():
    segs = [Segment(0.0, 2.5, "第一句"), Segment(2.5, 5.0, "第二句")]
    out = format_srt(segs)
    assert out.startswith("1\n")
    assert "\n2\n" in out
    assert "00:00:00,000 --> 00:00:02,500" in out
    assert "第一句" in out


def test_format_vtt_includes_header_and_dot():
    segs = [Segment(0.0, 2.5, "hi")]
    out = format_vtt(segs)
    assert out.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:02.500" in out


def test_format_txt_joins_without_timestamps():
    segs = [Segment(0.0, 1.0, "一"), Segment(1.0, 2.0, "二")]
    assert format_txt(segs) == "一\n二"


def test_format_lrc():
    segs = [Segment(0.0, 2.0, "一"), Segment(2.5, 5.0, "二")]
    assert format_lrc(segs) == "[00:00.00]一\n[00:02.50]二"


# -- Roundtrip --

def test_srt_roundtrip():
    segs_in = [Segment(0.0, 2.0, "A"), Segment(2.0, 5.5, "B")]
    out = format_srt(segs_in)
    segs_out = parse_srt(out)
    assert len(segs_out) == 2
    assert segs_out[0].text == "A"
    assert segs_out[1].start == 2.0
    assert segs_out[1].end == 5.5


# -- Whisper adapter --

def test_from_whisper_result_converts_segments():
    from unittest.mock import MagicMock
    fake = MagicMock()
    fake.segments = [
        MagicMock(start=0.0, end=1.0, text="hi"),
        MagicMock(start=1.0, end=2.5, text="bye"),
    ]
    segs = from_whisper_result(fake)
    assert len(segs) == 2
    assert segs[0].start == 0.0
    assert segs[0].text == "hi"
    assert isinstance(segs[0], Segment)
