"""Unit tests for app.services.document.translate_service.service.TranslateService."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.document.translate_service.service import (
    TranslateService,
    TASK_TYPE_DOCUMENT_TRANSLATE,
)
from app.services.document.translate_service import text as txt


def _fake_file_service(tmp_path, *, content: str, name: str) -> MagicMock:
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"
    fs.output_dir.mkdir()
    fs.upload_dir = tmp_path / "upload"
    fs.upload_dir.mkdir()
    src_path = tmp_path / name
    src_path.write_text(content, encoding="utf-8")
    fi = MagicMock(file_path=src_path, original_filename=name)
    fs.require_file.return_value = fi

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=Path(file_path).stat().st_size)
    fs.register_output.side_effect = _register_output
    return fs


def _fake_chat_service(text="translated"):
    cs = MagicMock()
    @contextmanager
    def _session_cm(*args, **kwargs):
        s = MagicMock()
        s.chat = MagicMock(return_value=text)
        s.complete = MagicMock(return_value=text)
        yield s
    cs.session = MagicMock(side_effect=_session_cm)
    return cs


def _make_svc(tmp_path, *, content: str, name: str):
    fs = _fake_file_service(tmp_path, content=content, name=name)
    tm = MagicMock()
    mm = MagicMock()
    cs = _fake_chat_service()
    rs = MagicMock()
    svc = TranslateService(
        file_service=fs, task_manager=tm, model_manager=mm,
        chat_service=cs, remote_service=rs,
    )
    return svc, fs, tm, mm, cs, rs


def test_init_registers_handler(tmp_path):
    svc, fs, tm, *_ = _make_svc(tmp_path, content="hi", name="a.txt")
    tm.register_handler.assert_called_once()
    args, kwargs = tm.register_handler.call_args
    assert args[0] == TASK_TYPE_DOCUMENT_TRANSLATE
    assert kwargs.get("output_policy") == "history"


@pytest.mark.asyncio
async def test_submit_translate_passes_all_params(tmp_path):
    svc, fs, tm, *_ = _make_svc(tmp_path, content="hi", name="a.txt")

    async def _async_submit(*a, **k):
        return "t1"
    tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

    task_id = await svc.submit_translate(
        file_id="fid", source_language="en", target_language="zh-TW",
        model_family="gemma4", model_size="4b",
        translate_style="formal", glossary={"AI": "人工智慧"},
        remote=False,
    )
    assert task_id == "t1"
    args, _ = tm.submit.call_args
    assert args[0] == TASK_TYPE_DOCUMENT_TRANSLATE
    p = args[1]
    assert p["file_id"] == "fid"
    assert p["source_language"] == "en"
    assert p["target_language"] == "zh-TW"
    assert p["translate_style"] == "formal"
    assert p["glossary"] == {"AI": "人工智慧"}
    assert p["remote"] is False


def test_execute_rejects_unsupported_format(tmp_path):
    svc, *_ = _make_svc(tmp_path, content="hi", name="a.pdf")
    with pytest.raises(ValueError, match="Unsupported file format"):
        svc._execute(
            {"file_id": "fid", "source_language": "en", "target_language": "zh-TW",
             "model_family": "gemma4", "model_size": "4b"},
            lambda p, m: None,
        )


def test_execute_text_local_path_calls_translate_text_local(tmp_path):
    svc, fs, *_rest = _make_svc(tmp_path, content="hello world", name="doc.txt")

    with patch("app.services.document.translate_service.text.translate_text_local",
               return_value="哈囉世界") as ttl:
        result = svc._execute(
            {"file_id": "fid", "source_language": "en", "target_language": "zh-TW",
             "model_family": "gemma4", "model_size": "4b"},
            lambda p, m: None,
        )
    ttl.assert_called_once()
    pos_args = ttl.call_args.args
    assert pos_args[0] == "hello world"
    assert result["translated_chars"] == len("哈囉世界")
    written = list(fs.output_dir.glob("doc_zh-TW.txt"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == "哈囉世界"


def test_execute_text_remote_path_calls_translate_text_cloud(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path, content="hello", name="doc.txt")
    prov = MagicMock()
    rs.get_provider_for_connection.return_value = prov

    with patch("app.services.document.translate_service.text.translate_text_cloud",
               return_value="哈囉") as ttc:
        result = svc._execute(
            {"file_id": "fid", "source_language": "en", "target_language": "zh-TW",
             "model_family": "gemma4", "model_size": "4b",
             "remote": True, "provider": "openai", "conn_id": 1, "remote_model": "gpt-4o"},
            lambda p, m: None,
        )
    ttc.assert_called_once()
    assert result["translated_chars"] == len("哈囉")
    assert (fs.output_dir / "doc_zh-TW.txt").read_text(encoding="utf-8") == "哈囉"


def test_execute_text_remote_raises_when_provider_unavailable(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path, content="hi", name="doc.txt")
    rs.get_provider_for_connection.return_value = None
    with pytest.raises(ValueError, match="No available openai connection"):
        svc._execute(
            {"file_id": "fid", "source_language": "en", "target_language": "zh-TW",
             "model_family": "gemma4", "model_size": "4b",
             "remote": True, "provider": "openai", "conn_id": 1, "remote_model": "gpt-4o"},
            lambda p, m: None,
        )


SAMPLE_SRT = (
    "1\n00:00:00,000 --> 00:00:01,000\nhello\n\n"
    "2\n00:00:01,000 --> 00:00:02,000\nworld\n"
)


def test_execute_subtitle_local_path_calls_translate_srt_auto(tmp_path):
    svc, fs, *_rest = _make_svc(tmp_path, content=SAMPLE_SRT, name="sub.srt")

    fake_translated = [{"start": 0.0, "end": 1.0, "text": "哈囉"},
                       {"start": 1.0, "end": 2.0, "text": "世界"}]
    with patch("app.pipeline.translate.translate_srt_auto",
               return_value=fake_translated) as tsa:
        result = svc._execute(
            {"file_id": "fid", "source_language": "en", "target_language": "zh-TW",
             "model_family": "gemma4", "model_size": "4b"},
            lambda p, m: None,
        )
    tsa.assert_called_once()
    kwargs = tsa.call_args.kwargs
    assert "session" in kwargs and kwargs["session"] is not None
    assert kwargs.get("prov") is None
    assert result["translated_chars"] == len("哈囉") + len("世界")
    assert (fs.output_dir / "sub_zh-TW.srt").exists()


def test_execute_subtitle_remote_path_calls_translate_srt_auto_with_prov(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path, content=SAMPLE_SRT, name="sub.srt")
    prov = MagicMock()
    rs.get_provider_for_connection.return_value = prov

    fake_translated = [{"start": 0.0, "end": 1.0, "text": "哈囉"}]
    with patch("app.pipeline.translate.translate_srt_auto",
               return_value=fake_translated) as tsa:
        svc._execute(
            {"file_id": "fid", "source_language": "en", "target_language": "zh-TW",
             "model_family": "gemma4", "model_size": "4b",
             "remote": True, "provider": "openai", "conn_id": 1, "remote_model": "gpt-4o"},
            lambda p, m: None,
        )
    kwargs = tsa.call_args.kwargs
    assert kwargs["prov"] is prov
    assert kwargs["remote_model"] == "gpt-4o"
    assert kwargs.get("session") is None


def test_execute_subtitle_remote_raises_when_provider_unavailable(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path, content=SAMPLE_SRT, name="sub.srt")
    rs.get_provider_for_connection.return_value = None
    with pytest.raises(ValueError, match="No available openai connection"):
        svc._execute(
            {"file_id": "fid", "source_language": "en", "target_language": "zh-TW",
             "model_family": "gemma4", "model_size": "4b",
             "remote": True, "provider": "openai", "conn_id": 1, "remote_model": "gpt-4o"},
            lambda p, m: None,
        )


def test_translate_text_cloud_routes_through_session_streaming():
    prov = MagicMock(name="prov")
    prov.chat = MagicMock(return_value="translated")
    cfg = {"temperature": 0.1, "max_tokens": 4096}
    with patch("app.adapters.ai.inference_config.get_remote_inference_config", return_value=cfg), \
         patch("app.services.document.translate_service.text._get_cloud_text_chunk_size", return_value=10_000):
        out = txt.translate_text_cloud("hello world", "en", "zh", prov, "gpt-4o")
    assert out == "translated"
    _, kwargs = prov.chat.call_args
    assert kwargs.get("abort_hook") is not None
    assert kwargs.get("model") == "gpt-4o"


def test_execute_emits_translate_complete_at_end(tmp_path):
    svc, fs, *_rest = _make_svc(tmp_path, content="hi", name="doc.txt")
    events = []
    def on_progress(p, m):
        events.append((p, m))

    with patch("app.services.document.translate_service.text.translate_text_local",
               return_value="哈囉"):
        svc._execute(
            {"file_id": "fid", "source_language": "en", "target_language": "zh-TW",
             "model_family": "gemma4", "model_size": "4b"},
            on_progress,
        )
    assert events[-1] == (1.0, "task.progress.translate_complete")
    for _, m in events:
        assert m.startswith("task.progress.")
