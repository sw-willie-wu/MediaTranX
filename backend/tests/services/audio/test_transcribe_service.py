"""Tests for AudioTranscribeService — transcribe + optional translate + summarize.

Pattern mirrors Wave D test_subtitle_service.py since the services are structurally
similar (whisper + chat_service + StageProgress)."""
from __future__ import annotations
import re
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_file_service_mock, make_model_manager_mock
from app.services.audio.transcribe_service.service import (
    AudioTranscribeService,
    TASK_TYPE_AUDIO_TRANSCRIBE,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _make_transcribe_result(segments=None, language="en"):
    """Build a fake transcribe_audio_sync return value."""
    seg = MagicMock(start=0.0, end=1.0, text="hello")
    result = MagicMock()
    result.segments = segments if segments is not None else [seg]
    result.language = language
    result.language_probability = 0.99
    result.duration = 1.0
    return result


def _bilingual_return(*, with_translation: bool):
    src = {"file_id": "src1", "filename": "v.en.txt", "size": 10, "language": "en"}
    if not with_translation:
        return [src]
    tgt = {"file_id": "tgt1", "filename": "v.zh-TW.txt", "size": 12, "language": "zh-TW"}
    return [src, tgt]


def _build(tmp_path):
    fs = make_file_service_mock(tmp_path)
    fs.read_text = MagicMock(return_value="hello\n")
    fs.output_dir = tmp_path / "out"
    fs.output_dir.mkdir(exist_ok=True)
    ffmpeg = MagicMock()
    ffmpeg.ffmpeg_path = "/fake/ffmpeg"
    mm = make_model_manager_mock()
    rs = MagicMock()
    cs = MagicMock()
    whisper = MagicMock()
    svc = AudioTranscribeService(
        file_service=fs, task_manager=MagicMock(),
        ffmpeg=ffmpeg, model_manager=mm,
        remote_service=rs, chat_service=cs,
        whisper=whisper,
    )
    Path(fs.require_file("f").file_path).write_bytes(b"audio")
    return svc, ffmpeg, mm, rs, cs, whisper, fs


BASE_PARAMS = {
    "file_id": "f",
    "language": "en",
    "model_size": "large-v3",
    "output_format": "txt",
    "vocal_separation": False,
    "align": False,
    "translate": False,
    "target_lang": None,
    "summarize": False,
}


class TestInit:
    def test_registers_handler_with_results_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        AudioTranscribeService(
            file_service=fs, task_manager=tm,
            ffmpeg=MagicMock(), model_manager=make_model_manager_mock(),
            remote_service=MagicMock(), chat_service=MagicMock(),
            whisper=MagicMock(),
        )
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_AUDIO_TRANSCRIBE
        assert kwargs.get("output_policy") == "results"


class TestSubmit:
    async def test_submit_forwards_kwargs(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async(*a, **k)

        svc = AudioTranscribeService(
            file_service=fs, task_manager=tm,
            ffmpeg=MagicMock(), model_manager=make_model_manager_mock(),
            remote_service=MagicMock(), chat_service=MagicMock(),
            whisper=MagicMock(),
        )
        tid = await svc.submit_transcribe(
            file_id="fid", language="ja", model_size="large-v3",
            output_format="srt", translate=True, target_lang="zh-TW",
        )
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_AUDIO_TRANSCRIBE
        assert args[1]["language"] == "ja"
        assert args[1]["translate"] is True
        assert args[1]["target_lang"] == "zh-TW"


class TestExecuteTranscribeOnly:
    def test_local_only_no_translate(self, tmp_path):
        svc, *_, fs = _build(tmp_path)
        with patch("app.services.audio.transcribe_service.service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.services.audio.transcribe_service.service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=False)):
            result = svc._execute(BASE_PARAMS, lambda p, m: None)

        assert result["translated"] is False
        assert result["summarized"] is False
        assert result["output_file_id"] == "src1"
        assert result["segment_count"] == 1


class TestExecuteWithTranslate:
    def test_local_translate_uses_chat_service_session(self, tmp_path):
        svc, _, _, _, cs, _, fs = _build(tmp_path)

        @contextmanager
        def _session_cm(**kw):
            yield MagicMock()
        cs.session = MagicMock(side_effect=_session_cm)

        translated_dicts = [{"start": 0.0, "end": 1.0, "text": "你好"}]
        with patch("app.services.audio.transcribe_service.service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.pipeline.translate.translate_srt_auto",
                   return_value=translated_dicts), \
             patch("app.services.audio.transcribe_service.service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=True)):
            result = svc._execute(
                {**BASE_PARAMS, "translate": True, "target_lang": "zh-TW",
                 "translate_remote": False, "translate_model_family": "qwen3",
                 "translate_model_size": "8b", "translate_quantization": "Q4_K_M"},
                lambda p, m: None,
            )
        cs.session.assert_called_once()
        assert result["translated"] is True
        assert result["target_language"] == "zh-TW"
        # Primary output is translated file
        assert result["output_file_id"] == "tgt1"

    def test_remote_translate_uses_provider(self, tmp_path):
        svc, _, _, rs, cs, _, fs = _build(tmp_path)
        fake_provider = MagicMock()
        rs.get_provider_for_connection = MagicMock(return_value=fake_provider)

        translated_dicts = [{"start": 0.0, "end": 1.0, "text": "你好"}]
        with patch("app.services.audio.transcribe_service.service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.pipeline.translate.translate_srt_auto",
                   return_value=translated_dicts) as mock_translate, \
             patch("app.services.audio.transcribe_service.service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=True)):
            svc._execute(
                {**BASE_PARAMS, "translate": True, "target_lang": "zh-TW",
                 "translate_remote": True, "translate_provider": "openai",
                 "translate_conn_id": "abc",
                 "translate_remote_model": "gpt-4o"},
                lambda p, m: None,
            )
        rs.get_provider_for_connection.assert_called_once()
        cs.session.assert_not_called()
        kw = mock_translate.call_args.kwargs
        assert kw.get("prov") is fake_provider

    def test_remote_translate_no_provider_raises(self, tmp_path):
        svc, _, _, rs, _, _, _ = _build(tmp_path)
        rs.get_provider_for_connection = MagicMock(return_value=None)
        with patch("app.services.audio.transcribe_service.service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()):
            with pytest.raises(ValueError, match="No available"):
                svc._execute(
                    {**BASE_PARAMS, "translate": True, "target_lang": "zh-TW",
                     "translate_remote": True, "translate_provider": "openai",
                     "translate_conn_id": "missing"},
                    lambda p, m: None,
                )


class TestExecuteWithSummarize:
    def test_local_summarize_uses_chat_service(self, tmp_path):
        svc, _, _, _, cs, _, fs = _build(tmp_path)

        @contextmanager
        def _session_cm(**kw):
            sess = MagicMock()
            sess.chat = MagicMock(return_value="summary text here")
            yield sess
        cs.session = MagicMock(side_effect=_session_cm)

        with patch("app.services.audio.transcribe_service.service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.services.audio.transcribe_service.service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=False)), \
             patch("app.services.audio.transcribe_service.summarize.map_reduce_summarize",
                   return_value="generated summary"), \
             patch("app.services.audio.transcribe_service.summarize.calc_chunk_budget",
                   return_value=1000), \
             patch("app.adapters.ai.inference_config.get_inference_config",
                   return_value={"temperature": 0.3, "top_k": 50, "top_p": 0.95,
                                 "n_ctx": 4096}):
            result = svc._execute(
                {**BASE_PARAMS, "summarize": True, "summarize_remote": False,
                 "summarize_model_family": "qwen3", "summarize_model_size": "8b",
                 "summarize_quantization": "Q4_K_M"},
                lambda p, m: None,
            )

        assert result["summarized"] is True
        cs.session.assert_called_once()
        # Summary file should be registered
        assert any(f.get("type") == "summary" for f in result["output_files"])


class TestProgress:
    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, *_, _ = _build(tmp_path)
        progress = []
        with patch("app.services.audio.transcribe_service.service.transcribe_audio_sync",
                   return_value=_make_transcribe_result()), \
             patch("app.services.audio.transcribe_service.service.write_bilingual_or_single",
                   return_value=_bilingual_return(with_translation=False)):
            svc._execute(BASE_PARAMS, lambda p, m: progress.append((p, m)))
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0


class TestQueryMethods:
    def test_get_model_status_delegates_to_whisper(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        whisper = MagicMock()
        whisper.get_model_status = MagicMock(return_value={"available": True})
        svc = AudioTranscribeService(
            file_service=fs, task_manager=MagicMock(),
            ffmpeg=MagicMock(), model_manager=make_model_manager_mock(),
            remote_service=MagicMock(), chat_service=MagicMock(),
            whisper=whisper,
        )
        status = svc.get_model_status("large-v3")
        whisper.get_model_status.assert_called_once_with("large-v3")
        assert status == {"available": True}
