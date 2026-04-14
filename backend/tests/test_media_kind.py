import pytest
from app.utils.media_kind import infer_kind, MediaKind


@pytest.mark.parametrize("filename,expected", [
    ("photo.jpg", MediaKind.IMAGE),
    ("photo.PNG", MediaKind.IMAGE),
    ("photo.webp", MediaKind.IMAGE),
    ("song.mp3", MediaKind.AUDIO),
    ("song.wav", MediaKind.AUDIO),
    ("song.flac", MediaKind.AUDIO),
    ("song.mid", MediaKind.AUDIO),
    ("clip.mp4", MediaKind.VIDEO),
    ("clip.mov", MediaKind.VIDEO),
    ("clip.webm", MediaKind.VIDEO),
    ("doc.pdf", MediaKind.DOCUMENT),
    ("doc.docx", MediaKind.DOCUMENT),
    ("doc.srt", MediaKind.DOCUMENT),
    ("doc.vtt", MediaKind.DOCUMENT),
    ("doc.md", MediaKind.DOCUMENT),
    ("doc.txt", MediaKind.DOCUMENT),
    ("doc.json", MediaKind.DOCUMENT),
])
def test_infer_kind_by_extension(filename, expected):
    assert infer_kind(filename) == expected


def test_infer_kind_unknown_returns_none():
    assert infer_kind("file.xyz") is None
    assert infer_kind("noext") is None
