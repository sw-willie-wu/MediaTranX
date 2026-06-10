"""Service-level @pytest.mark.ai integration tests.

These tests exercise the full service path: container DI → service.submit →
service._execute → real wrapper → real model. They're the only tests that
catch bugs in the wrapper-acquire / chat_service.session / mm.acquire wiring
end-to-end (bugs #2/#3/#7/#8/#9 were all here, masked because no test in this
suite reached this layer).

Requires: GPU + downloaded models (Real-ESRGAN, Whisper large-v3, Qwen3 8B,
Qwen3-VL 8B). Run with `pytest -m ai`. Skipif when models missing.
"""
from __future__ import annotations
import tempfile
import wave
from pathlib import Path

import pytest
from PIL import Image

pytestmark = pytest.mark.ai


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _container():
    """Get a fully-wired container. Reuse across tests in the same session is
    safe because container.init_container() is idempotent (overwrites the
    module-level singleton)."""
    from app.init.container import init_container
    return init_container()


def _model_downloaded(model_id: str, variant: str | None = None) -> bool:
    c = _container()
    return c.model_manager().get_model_path(model_id, variant) is not None


def _whisper_large_v3_downloaded() -> bool:
    """Whisper's get_model_path uses a different lookup; check disk directly."""
    from app.init.configs import SETTINGS
    d = SETTINGS.path.models / "whisper" / "large-v3"
    return (d / "model.bin").exists() and (
        (d / "vocabulary.txt").exists() or (d / "vocabulary.json").exists()
    )


def _make_image(tmp_path: Path, size=(32, 32), color=(128, 128, 128)) -> Path:
    p = tmp_path / "input.png"
    Image.new("RGB", size, color).save(p)
    return p


def _make_silent_wav(tmp_path: Path, duration_s: int = 1) -> Path:
    p = tmp_path / "silence.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * duration_s)
    return p


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestImageUpscaleService:
    """Bug #3/#8 path: upscale_service → upscaler.enhance → self.acquire →
    mm.acquire('upscale', family) → dispatcher → wrapper.run_inference."""

    def test_realesrgan_x4plus_end_to_end(self, tmp_path):
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PTH
        if not _model_downloaded("realesrgan", "x4plus"):
            pytest.skip("Real-ESRGAN x4plus model not downloaded")

        c = _container()
        svc = c.image_upscale()
        fd = c.file_service().register_local_file(str(_make_image(tmp_path)))

        result = svc._handle_task(
            {"file_id": fd.file_id, "model_id": "realesrgan-x4plus", "scale": 4,
             "sharpen": False, "face_fix": False, "face_restore_model_id": None,
             "face_restore_upscale": 2},
            lambda p, m: None,
        )

        assert result.get("output_file_id")
        # Output file actually exists on disk + 4x larger than 32x32 input
        out_filename = result.get("output_filename", "")
        out_path = c.file_service().output_dir / out_filename
        assert out_path.exists()
        with Image.open(out_path) as img:
            assert img.size == (128, 128)  # 32 * 4 = 128


class TestImageOcrService:
    """Bug #7 path: image_ocr → chat_service.session → llama_runtime.acquire →
    mm.acquire('llm', model, variant) → LlmWrapper.load → llama-server.start."""

    def test_qwen3vl_8b_end_to_end(self, tmp_path):
        if not _model_downloaded("qwen3vl", "8b:Q4_K_M"):
            pytest.skip("Qwen3-VL 8B Q4_K_M not downloaded")

        c = _container()
        svc = c.image_ocr()
        # White image — likely returns empty text or "no text found"
        fd = c.file_service().register_local_file(
            str(_make_image(tmp_path, (256, 256), color=(255, 255, 255)))
        )

        result = svc._handle_task(
            {"file_id": fd.file_id, "model_family": "qwen3vl",
             "model_size": "8b", "quantization": "Q4_K_M", "output_format": "md"},
            lambda p, m: None,
        )

        assert result.get("output_file_id")
        out_filename = result.get("output_filename", "")
        out_path = c.file_service().output_dir / out_filename
        assert out_path.exists()


class TestAudioTranscribeService:
    """Bug #2/#9 path: audio_transcribe → transcribe_audio_sync →
    whisper.transcribe → self.acquire → mm.acquire('whisper', ...) →
    WhisperWrapper.load → faster_whisper.WhisperModel."""

    def test_whisper_large_v3_end_to_end(self, tmp_path):
        if not _whisper_large_v3_downloaded():
            pytest.skip("Whisper large-v3 model not downloaded")

        c = _container()
        svc = c.audio_transcribe()
        fd = c.file_service().register_local_file(str(_make_silent_wav(tmp_path)))

        result = svc._handle_task(
            {"file_id": fd.file_id, "source_language": "en", "model_size": "large-v3",
             "output_format": "txt", "vocal_separation": False, "align": False,
             "translate": False, "target_language": None, "summarize": False},
            lambda p, m: None,
        )

        assert result.get("output_file_id")
        assert result.get("translated") is False
        assert result.get("summarized") is False
        assert "detected_language" in result
        # Silent audio → 0 segments expected
        assert isinstance(result.get("segment_count"), int)


class TestVideoSubtitleService:
    """Bug #2 (whisper unload) + #9 (whisper _model_manager) path. Skip the
    translate branch since that's covered by AudioTranscribeService."""

    def test_whisper_only_end_to_end(self, tmp_path):
        if not _whisper_large_v3_downloaded():
            pytest.skip("Whisper large-v3 model not downloaded")

        c = _container()
        svc = c.video_subtitle()
        # Use a silent wav as input — whisper handles audio files
        fd = c.file_service().register_local_file(str(_make_silent_wav(tmp_path)))

        result = svc._handle_task(
            {"file_id": fd.file_id, "language": "en", "model_size": "large-v3",
             "output_format": "srt", "target_language": None,
             "vocal_separation": False, "align": False},
            lambda p, m: None,
        )

        assert result.get("output_file_id")
        assert result.get("translated") is False


class TestDocumentTranslateText:
    """Bug #7 path: translate_text_local must be called inside chat_service.session()
    which goes through llama_runtime.acquire → mm.acquire('llm', ...)."""

    def test_local_translate_text_end_to_end(self):
        if not _model_downloaded("qwen3", "8b:Q4_K_M"):
            pytest.skip("Qwen3 8B Q4_K_M not downloaded")

        from app.services.document.translate_service.text import translate_text_local
        c = _container()

        with c.chat_service().session(
            model_family="qwen3", model_size="8b", quantization="Q4_K_M",
        ) as session:
            result = translate_text_local(
                text="Hello world.",
                source_lang="en", target_lang="zh-TW",
                session=session,
                model_family="qwen3", model_size="8b",
            )

        assert isinstance(result, str)
        assert len(result) > 0
        # Should produce SOME Chinese chars (very loose check; LLM output varies)
        assert any("一" <= ch <= "鿿" for ch in result), (
            f"Expected Chinese output, got: {result!r}"
        )


class TestAudioLyricsService:
    """Bug #2 (whisper unload) + bug #9 (whisper _model_manager) path for
    lyrics service. Skip translate branch (covered by transcribe test)."""

    def test_local_whisper_only_end_to_end(self, tmp_path):
        if not _whisper_large_v3_downloaded():
            pytest.skip("Whisper large-v3 model not downloaded")

        c = _container()
        svc = c.audio_lyrics()
        fd = c.file_service().register_local_file(str(_make_silent_wav(tmp_path)))

        result = svc._handle_task(
            # lyrics service uses `whisper_size` (not `model_size`)
            {"file_id": fd.file_id, "language": "en", "whisper_size": "large-v3",
             "output_format": "lrc",
             "vocal_separation": False, "translate": False, "target_lang": None,
             "translate_model_family": "qwen3", "translate_model_size": "8b",
             "translate_quantization": "Q4_K_M"},
            lambda p, m: None,
        )

        assert result.get("output_file_id")
