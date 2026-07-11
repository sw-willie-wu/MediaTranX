"""media_kind: .lrc 歌詞檔必須有歸類（pipeline 前置修）。"""
from app.workers.media_kind import MediaKind, infer_kind


def test_lrc_classified_as_document():
    assert infer_kind("song.lrc") == MediaKind.DOCUMENT
    assert infer_kind("SONG.LRC") == MediaKind.DOCUMENT


def test_existing_kinds_unchanged():
    assert infer_kind("a.srt") == MediaKind.DOCUMENT
    assert infer_kind("b.apng") == MediaKind.IMAGE
    assert infer_kind("c.opus") == MediaKind.AUDIO
    assert infer_kind("d.m4v") == MediaKind.VIDEO
    assert infer_kind("e.xyz") is None
