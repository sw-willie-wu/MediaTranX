"""Tests for SubtitleService — multi-stage extract/transcribe/translate/write."""
from __future__ import annotations
import re
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_file_service_mock, make_model_manager_mock
from app.adapters.binary.ffmpeg import MediaInfo
from app.services.video.subtitle_service import (
    SubtitleService,
    TASK_TYPE_VIDEO_SUBTITLE_GENERATE,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _make_media_info_with_audio():
    return MediaInfo(
        duration=10.0, width=1920, height=1080,
        fps=30.0, fps_fraction=Fraction(30, 1),
        video_codec="h264", audio_codec="aac",
        bitrate=1000, file_size=1024,
    )


def _make_media_info_no_audio():
    return MediaInfo(
        duration=10.0, width=1920, height=1080,
        fps=30.0, fps_fraction=Fraction(30, 1),
        video_codec="h264", audio_codec="",  # empty → falsy
        bitrate=1000, file_size=1024,
    )


def _make_transcribe_result(segments=None, language="en"):
    """Build a fake transcribe result with .segments/.language/.language_probability/.duration."""
    result = MagicMock()
    if segments is None:
        seg = MagicMock(start=0.0, end=1.0, text="hello")
        segments = [seg]
    result.segments = segments
    result.language = language
    result.language_probability = 0.99
    result.duration = 1.0
    return result


def _bilingual_return(*, with_translation: bool):
    """write_bilingual_or_single returns list[dict]."""
    src = {"file_id": "src1", "filename": "v.en.srt", "size": 100, "language": "en"}
    if not with_translation:
        return [src]
    tgt = {"file_id": "tgt1", "filename": "v.zh-TW.srt", "size": 120, "language": "zh-TW"}
    return [src, tgt]


def _build(tmp_path):
    fs = make_file_service_mock(tmp_path)
    ffmpeg = MagicMock()
    ffmpeg.ffmpeg_path = "/fake/ffmpeg"
    ffmpeg.get_media_info_sync = MagicMock(return_value=_make_media_info_with_audio())
    mm = make_model_manager_mock()
    rs = MagicMock()
    cs = MagicMock()
    whisper = MagicMock()
    svc = SubtitleService(
        ffmpeg=ffmpeg, file_service=fs, task_manager=MagicMock(),
        model_manager=mm, remote_service=rs, chat_service=cs,
        whisper=whisper,
    )
    Path(fs.require_file("f").file_path).write_bytes(b"v")
    return svc, ffmpeg, mm, rs, cs, whisper, fs


BASE_PARAMS = {
    "file_id": "f",
    "source_language": None,
    "model_size": "medium",
    "output_format": "srt",
    "target_language": None,
    "translate_model_size": "4b",
    "translate_model_family": "gemma4",
    "translate_quantization": None,
    "word_timestamps": False,
    "condition_on_previous_text": True,
    "min_silence_duration_ms": 200,
    "vad_threshold": 0.3,
    "keep_names": True,
    "translate_style": "colloquial",
    "glossary": None,
    "vocal_separation": False,
    "align": False,
}


class TestInit:
    def test_registers_handler_with_results_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        SubtitleService(
            ffmpeg=MagicMock(), file_service=fs, task_manager=tm,
            model_manager=make_model_manager_mock(),
            remote_service=MagicMock(), chat_service=MagicMock(),
            whisper=MagicMock(),
        )
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_VIDEO_SUBTITLE_GENERATE
        assert kwargs.get("output_policy") == "results"


class TestSubmit:
    async def test_submit_forwards_params(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = SubtitleService(
            ffmpeg=MagicMock(), file_service=fs, task_manager=tm,
            model_manager=make_model_manager_mock(),
            remote_service=MagicMock(), chat_service=MagicMock(),
            whisper=MagicMock(),
        )
        tid = await svc.submit_subtitle_generate(
            file_id="fid", source_language="en", model_size="large",
            output_format="srt", target_language="zh-TW",
        )
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_VIDEO_SUBTITLE_GENERATE
        assert args[1]["source_language"] == "en"
        assert args[1]["target_language"] == "zh-TW"


class TestExecuteLocalOnly:
    def test_no_audio_raises(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)
        ffmpeg.get_media_info_sync.return_value = _make_media_info_no_audio()
        with pytest.raises(ValueError, match="No audio track"):
            svc._execute(BASE_PARAMS, lambda p, m: None)

    def test_local_only_calls_extract_and_transcribe(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)
        with patch("app.services.video.subtitle_service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()) as mock_trans, \
             patch("app.services.video.subtitle_service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=False)) as mock_write:
            result = svc._execute(BASE_PARAMS, lambda p, m: None)
        ffmpeg.extract_audio_sync.assert_called_once()
        kwargs = ffmpeg.extract_audio_sync.call_args.kwargs
        assert kwargs["audio_format"] == "wav"
        assert kwargs["sample_rate"] == 16000
        assert kwargs["channels"] == 1
        mock_trans.assert_called_once()
        mock_write.assert_called_once()
        cs.session.assert_not_called()  # No translate path
        assert result["translated"] is False
        assert result["output_file_id"] == "src1"

    def test_temp_audio_cleaned_up_on_success(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)
        with patch("app.services.video.subtitle_service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.services.video.subtitle_service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=False)):
            # Simulate extract_audio_sync actually creating the temp file
            def _create_temp(input_path, output_path, **kw):
                Path(output_path).write_bytes(b"WAV")
            ffmpeg.extract_audio_sync.side_effect = _create_temp
            svc._execute(BASE_PARAMS, lambda p, m: None)
        # No leftover temp_audio_* in upload_dir
        leftovers = list(fs.upload_dir.glob("temp_audio_*.wav"))
        assert not leftovers

    def test_unsupported_output_format_raises(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)
        with patch("app.services.video.subtitle_service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()):
            with pytest.raises(ValueError, match="Unsupported output format"):
                svc._execute({**BASE_PARAMS, "output_format": "ass"}, lambda p, m: None)


class TestExecuteLocalTranslate:
    def test_local_translate_uses_chat_service_session(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)

        @contextmanager
        def _session_cm(**kw):
            yield MagicMock()
        cs.session = MagicMock(side_effect=_session_cm)

        translated_dicts = [{"start": 0.0, "end": 1.0, "text": "你好"}]
        with patch("app.services.video.subtitle_service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.pipeline.translate.translate_srt_auto",
                   return_value=translated_dicts) as mock_translate, \
             patch("app.services.video.subtitle_service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=True)):
            result = svc._execute(
                {**BASE_PARAMS, "target_language": "zh-TW", "translate_remote": False},
                lambda p, m: None,
            )
        cs.session.assert_called_once()
        mock_translate.assert_called_once()
        # session kwarg should be present
        kw = mock_translate.call_args.kwargs
        assert "session" in kw
        # Primary output is the translated file
        assert result["output_file_id"] == "tgt1"
        assert result["translated"] is True
        assert result["target_language"] == "zh-TW"


class TestExecuteRemoteTranslate:
    def test_remote_translate_uses_remote_service_provider(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)
        fake_provider = MagicMock()
        rs.get_provider_for_connection = MagicMock(return_value=fake_provider)

        translated_dicts = [{"start": 0.0, "end": 1.0, "text": "你好"}]
        with patch("app.services.video.subtitle_service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.pipeline.translate.translate_srt_auto",
                   return_value=translated_dicts) as mock_translate, \
             patch("app.services.video.subtitle_service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=True)):
            svc._execute(
                {**BASE_PARAMS, "target_language": "zh-TW",
                 "translate_remote": True, "translate_provider": "openai",
                 "translate_conn_id": "conn-1", "translate_remote_model": "gpt-4o"},
                lambda p, m: None,
            )
        rs.get_provider_for_connection.assert_called_once()
        cs.session.assert_not_called()  # remote skips local session
        kw = mock_translate.call_args.kwargs
        assert kw.get("prov") is fake_provider
        assert kw.get("remote_model") == "gpt-4o"

    def test_remote_translate_no_provider_raises(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)
        rs.get_provider_for_connection = MagicMock(return_value=None)
        with patch("app.services.video.subtitle_service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()):
            with pytest.raises(ValueError, match="No available"):
                svc._execute(
                    {**BASE_PARAMS, "target_language": "zh-TW",
                     "translate_remote": True, "translate_provider": "openai",
                     "translate_conn_id": "missing"},
                    lambda p, m: None,
                )


class TestBilingualOutput:
    def test_output_files_have_type_annotations(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)

        @contextmanager
        def _session_cm(**kw):
            yield MagicMock()
        cs.session = MagicMock(side_effect=_session_cm)

        translated_dicts = [{"start": 0.0, "end": 1.0, "text": "你好"}]
        with patch("app.services.video.subtitle_service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.pipeline.translate.translate_srt_auto",
                   return_value=translated_dicts), \
             patch("app.services.video.subtitle_service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=True)):
            result = svc._execute(
                {**BASE_PARAMS, "target_language": "zh-TW", "translate_remote": False},
                lambda p, m: None,
            )
        assert len(result["output_files"]) == 2
        assert result["output_files"][0]["type"] == "source"
        assert result["output_files"][1]["type"] == "translated"


class TestProgress:
    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, ffmpeg, mm, rs, cs, whisper, fs = _build(tmp_path)
        progress = []
        with patch("app.services.video.subtitle_service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.services.video.subtitle_service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=False)):
            svc._execute(BASE_PARAMS, lambda p, m: progress.append((p, m)))
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"


class TestQueryMethods:
    def test_get_model_status_delegates_to_whisper(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        whisper = MagicMock()
        whisper.get_model_status = MagicMock(return_value={"available": True})
        svc = SubtitleService(
            ffmpeg=MagicMock(), file_service=fs, task_manager=MagicMock(),
            model_manager=make_model_manager_mock(),
            remote_service=MagicMock(), chat_service=MagicMock(),
            whisper=whisper,
        )
        status = svc.get_model_status("medium")
        whisper.get_model_status.assert_called_once_with("medium")
        assert status == {"available": True}
