from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.utils.bilingual_output import write_bilingual_or_single


def _fake_file_service():
    fs = MagicMock()
    fs.register_output.side_effect = lambda file_id, file_path, original_filename: MagicMock(
        filename=file_path.name, file_size=file_path.stat().st_size
    )
    return fs


def test_single_output_writes_one_file(tmp_path):
    fs = _fake_file_service()
    out = write_bilingual_or_single(
        source_filename="x.zh.srt",
        source_text="foo",
        source_lang="zh",
        target_filename=None,
        target_text=None,
        target_lang=None,
        output_dir=tmp_path,
        original_filename="orig.mp4",
        file_service=fs,
    )
    assert len(out) == 1
    assert out[0]["language"] == "zh"
    assert out[0]["filename"] == "x.zh.srt"
    assert (tmp_path / "x.zh.srt").read_text(encoding="utf-8") == "foo"
    assert out[0]["size"] == len("foo")


def test_bilingual_writes_two_files_in_order(tmp_path):
    fs = _fake_file_service()
    out = write_bilingual_or_single(
        source_filename="x.zh.srt",
        source_text="foo",
        source_lang="zh",
        target_filename="x.en.srt",
        target_text="bar",
        target_lang="en",
        output_dir=tmp_path,
        original_filename="orig.mp4",
        file_service=fs,
    )
    assert len(out) == 2
    assert out[0]["language"] == "zh"
    assert out[1]["language"] == "en"
    assert out[0]["filename"] == "x.zh.srt"
    assert out[1]["filename"] == "x.en.srt"
    assert (tmp_path / "x.zh.srt").read_text(encoding="utf-8") == "foo"
    assert (tmp_path / "x.en.srt").read_text(encoding="utf-8") == "bar"


def test_bilingual_returns_unique_file_ids(tmp_path):
    fs = _fake_file_service()
    out = write_bilingual_or_single(
        source_filename="a.ja.lrc",
        source_text="a",
        source_lang="ja",
        target_filename="a.en.lrc",
        target_text="b",
        target_lang="en",
        output_dir=tmp_path,
        original_filename="orig",
        file_service=fs,
    )
    assert out[0]["file_id"] != out[1]["file_id"]


def test_creates_output_dir_if_missing(tmp_path):
    fs = _fake_file_service()
    out_dir = tmp_path / "new" / "nested"
    assert not out_dir.exists()
    out = write_bilingual_or_single(
        source_filename="x.txt",
        source_text="hi",
        source_lang="en",
        target_filename=None,
        target_text=None,
        target_lang=None,
        output_dir=out_dir,
        original_filename="o",
        file_service=fs,
    )
    assert out_dir.exists()
    assert len(out) == 1


def test_mismatched_target_params_raises(tmp_path):
    fs = _fake_file_service()
    with pytest.raises(ValueError):
        write_bilingual_or_single(
            source_filename="x.srt",
            source_text="s",
            source_lang="en",
            target_filename="y.srt",
            target_text=None,  # mismatch
            target_lang="zh",
            output_dir=tmp_path,
            original_filename="o",
            file_service=fs,
        )
    with pytest.raises(ValueError):
        write_bilingual_or_single(
            source_filename="x.srt",
            source_text="s",
            source_lang="en",
            target_filename=None,  # mismatch
            target_text="t",
            target_lang="zh",
            output_dir=tmp_path,
            original_filename="o",
            file_service=fs,
        )


def test_register_output_called_with_correct_args(tmp_path):
    fs = _fake_file_service()
    out = write_bilingual_or_single(
        source_filename="foo.ja.srt",
        source_text="x",
        source_lang="ja",
        target_filename="foo.en.srt",
        target_text="y",
        target_lang="en",
        output_dir=tmp_path,
        original_filename="original.mp4",
        file_service=fs,
    )
    assert fs.register_output.call_count == 2
    calls = fs.register_output.call_args_list
    assert calls[0].kwargs["original_filename"] == "original.mp4"
    assert calls[0].kwargs["file_id"] == out[0]["file_id"]
    assert calls[0].kwargs["file_path"] == tmp_path / "foo.ja.srt"
    assert calls[1].kwargs["file_id"] == out[1]["file_id"]
    assert calls[1].kwargs["file_path"] == tmp_path / "foo.en.srt"
