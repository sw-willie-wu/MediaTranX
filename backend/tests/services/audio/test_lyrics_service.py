"""Unit tests for app.services.audio.lyrics_service."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.ai.wrapper.whisper import TranscribeSegment
from app.services.audio.lyrics_service import AudioLyricsService, TASK_TYPE_AUDIO_LYRICS
from tests.conftest import make_model_manager_mock


def _fake_chat_service():
    cs = MagicMock()
    @contextmanager
    def _session_cm(*args, **kwargs):
        yield MagicMock()
    cs.session = MagicMock(side_effect=_session_cm)
    return cs


def _make_svc(tmp_path):
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"; fs.output_dir.mkdir()
    src = tmp_path / "song.mp3"; src.write_bytes(b"\x00")
    fi = MagicMock(file_path=src, original_filename="song.mp3")
    fs.require_file.return_value = fi

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=0)
    fs.register_output.side_effect = _register_output
    fs.read_text = MagicMock(return_value="line 1\nline 2")

    tm = MagicMock()
    ffmpeg = MagicMock()
    ffmpeg.ffmpeg_path = "/usr/bin/ffmpeg"
    mm = make_model_manager_mock()
    rs = MagicMock()
    cs = _fake_chat_service()
    whisper = MagicMock()
    demucs = MagicMock()
    align = MagicMock()
    svc = AudioLyricsService(
        file_service=fs, task_manager=tm, ffmpeg=ffmpeg,
        model_manager=mm, remote_service=rs, chat_service=cs,
        whisper=whisper, demucs=demucs, alignment_engine=align,
    )
    return svc, fs, tm, ffmpeg, mm, rs, cs, whisper, demucs, align


def _fake_transcribe_result(segments=None, language="en"):
    """Build a TranscribeResult-shaped MagicMock."""
    if segments is None:
        segments = [TranscribeSegment(0.0, 1.0, "hello"), TranscribeSegment(1.0, 2.0, "world")]
    r = MagicMock()
    r.segments = segments
    r.language = language
    return r


def test_init_registers_handler(tmp_path):
    svc, fs, tm, *_ = _make_svc(tmp_path)
    tm.register_handler.assert_called_once()
    args, kwargs = tm.register_handler.call_args
    assert args[0] == TASK_TYPE_AUDIO_LYRICS
    assert kwargs.get("output_policy") == "results"


@pytest.mark.asyncio
async def test_submit_lyrics_passes_params(tmp_path):
    svc, fs, tm, *_ = _make_svc(tmp_path)
    async def _submit(*a, **k): return "tl"
    tm.submit.side_effect = lambda *a, **k: _submit(*a, **k)
    task_id = await svc.submit_lyrics(
        file_id="fid", model_size="medium",
        translate=True, target_language="zh-TW",
    )
    assert task_id == "tl"
    args, _ = tm.submit.call_args
    p = args[1]
    assert p["model_size"] == "medium"
    assert p["translate"] is True
    assert p["target_language"] == "zh-TW"


def test_execute_no_translate_writes_single_lrc(tmp_path):
    svc, fs, *_rest = _make_svc(tmp_path)
    with patch("app.services.audio.lyrics_service.transcribe_audio_sync",
               return_value=_fake_transcribe_result()):
        result = svc._execute({
            "file_id": "fid", "model_size": "medium",
            "translate": False, "output_format": "lrc",
        }, lambda p, m: None)
    assert result["translated"] is False
    assert result["segment_count"] == 2
    assert len(result["output_files"]) == 1
    assert result["output_files"][0]["filename"].endswith(".lrc")


def test_execute_translate_local_uses_chat_session(tmp_path):
    svc, fs, tm, ffmpeg, mm, rs, cs, *_ = _make_svc(tmp_path)
    fake_translated = [
        {"start": 0.0, "end": 1.0, "text": "哈囉"},
        {"start": 1.0, "end": 2.0, "text": "世界"},
    ]
    with patch("app.services.audio.lyrics_service.transcribe_audio_sync",
               return_value=_fake_transcribe_result(language="en")), \
         patch("app.pipeline.translate.translate_srt_auto",
               return_value=fake_translated) as tsa:
        result = svc._execute({
            "file_id": "fid", "model_size": "medium",
            "translate": True, "target_language": "zh-TW",
            "translate_model_family": "gemma4", "translate_model_size": "4b",
            "translate_remote": False, "output_format": "lrc",
        }, lambda p, m: None)
    assert result["translated"] is True
    cs.session.assert_called_once()
    kwargs = tsa.call_args.kwargs
    assert "session" in kwargs and kwargs["session"] is not None
    assert len(result["output_files"]) == 2


def test_execute_translate_remote_uses_provider(tmp_path):
    svc, fs, tm, ffmpeg, mm, rs, cs, *_ = _make_svc(tmp_path)
    prov = MagicMock()
    rs.get_provider_for_connection.return_value = prov
    fake_translated = [{"start": 0.0, "end": 1.0, "text": "哈囉"}]
    with patch("app.services.audio.lyrics_service.transcribe_audio_sync",
               return_value=_fake_transcribe_result(
                   segments=[TranscribeSegment(0.0, 1.0, "hello")])), \
         patch("app.pipeline.translate.translate_srt_auto",
               return_value=fake_translated) as tsa:
        svc._execute({
            "file_id": "fid", "model_size": "medium",
            "translate": True, "target_language": "zh-TW",
            "translate_remote": True, "translate_provider": "openai",
            "translate_conn_id": 1, "translate_remote_model": "gpt-4o",
            "output_format": "lrc",
        }, lambda p, m: None)
    kwargs = tsa.call_args.kwargs
    assert kwargs["prov"] is prov
    # Remote branch passes no `session` kwarg at all (not even None)
    assert "session" not in kwargs
    assert not cs.session.called


def test_execute_translate_remote_raises_when_provider_unavailable(tmp_path):
    svc, fs, tm, ffmpeg, mm, rs, *_ = _make_svc(tmp_path)
    rs.get_provider_for_connection.return_value = None
    with patch("app.services.audio.lyrics_service.transcribe_audio_sync",
               return_value=_fake_transcribe_result()):
        with pytest.raises(ValueError, match="No available openai connection"):
            svc._execute({
                "file_id": "fid", "model_size": "medium",
                "translate": True, "target_language": "zh-TW",
                "translate_remote": True, "translate_provider": "openai",
                "translate_conn_id": 1, "translate_remote_model": "gpt-4o",
                "output_format": "lrc",
            }, lambda p, m: None)


def test_execute_emits_progress_keys_only(tmp_path):
    """Every emitted message must match `task.progress.<name>(|<arg>)*` regex."""
    import re
    progress_re = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")
    svc, fs, *_rest = _make_svc(tmp_path)
    events = []
    def cb(p, m): events.append((p, m))
    with patch("app.services.audio.lyrics_service.transcribe_audio_sync",
               return_value=_fake_transcribe_result()):
        svc._execute({
            "file_id": "fid", "model_size": "medium",
            "translate": False, "output_format": "lrc",
        }, cb)
    bad = [m for _, m in events if not progress_re.match(m)]
    assert not bad, f"Non-i18n progress messages: {bad}"
    assert events[-1] == (1.0, "task.progress.lyrics_complete")


def test_execute_output_format_txt_writes_txt_file(tmp_path):
    """Cover the format=='txt' branch in _format_output — lrc is tested elsewhere."""
    svc, fs, *_rest = _make_svc(tmp_path)
    with patch("app.services.audio.lyrics_service.transcribe_audio_sync",
               return_value=_fake_transcribe_result()):
        result = svc._execute({
            "file_id": "fid", "model_size": "medium",
            "translate": False, "output_format": "txt",
        }, lambda p, m: None)
    assert len(result["output_files"]) == 1
    assert result["output_files"][0]["filename"].endswith(".txt")
