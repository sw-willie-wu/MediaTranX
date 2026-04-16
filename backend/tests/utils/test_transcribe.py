from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.transcribe import (
    TranscribeOptions,
    _build_stage_list,
    _make_stage_progress,
    transcribe_audio_sync,
)


def test_build_stage_list_whisper_only():
    opts = TranscribeOptions()
    assert _build_stage_list(opts) == ["whisper"]


def test_build_stage_list_with_demucs_and_align():
    opts = TranscribeOptions(separate_vocals=True, align=True)
    assert _build_stage_list(opts) == ["demucs", "whisper", "align"]


def test_stage_progress_remaps_correctly():
    events: list[tuple[float, str]] = []
    sp = _make_stage_progress(["whisper"], lambda p, m: events.append((p, m)))
    sp("whisper", 0.5, "task.progress.x")
    assert events == [(0.5, "task.progress.x")]


def test_stage_progress_weighted_composition():
    events: list[tuple[float, str]] = []
    sp = _make_stage_progress(["demucs", "whisper", "align"], lambda p, m: events.append((p, m)))
    # demucs=3, whisper=5, align=1, total=9
    sp("demucs", 1.0, "a")
    sp("whisper", 0.5, "b")  # prior=3, this=5*0.5=2.5, overall=5.5/9
    sp("align", 1.0, "c")    # prior=8, this=1, overall=9/9
    assert abs(events[0][0] - 3/9) < 1e-6
    assert abs(events[1][0] - 5.5/9) < 1e-6
    assert abs(events[2][0] - 1.0) < 1e-6


def test_stage_progress_noop_when_callback_none():
    sp = _make_stage_progress(["whisper"], None)
    # Should not raise
    sp("whisper", 0.5, "anything")


def test_transcribe_audio_sync_whisper_only(monkeypatch, tmp_path):
    """Happy path: no demucs, no align."""
    fake_whisper = MagicMock()
    fake_result = MagicMock(
        segments=[MagicMock(start=0.0, end=1.0, text="hi")],
        language="en",
    )
    fake_whisper.transcribe.return_value = fake_result

    fake_manager = MagicMock()
    fake_manager.gpu_session.return_value.__enter__ = lambda *a: None
    fake_manager.gpu_session.return_value.__exit__ = lambda *a: None

    fake_container = MagicMock()
    fake_container.model_manager.return_value = fake_manager

    monkeypatch.setattr("app.engine.ai.audio.whisper.get_whisper", lambda: fake_whisper)
    monkeypatch.setattr("app.init.container.get_container", lambda: fake_container)

    opts = TranscribeOptions(model_size="tiny")
    result = transcribe_audio_sync(tmp_path / "x.wav", opts)

    assert result is fake_result
    fake_whisper.transcribe.assert_called_once()


def test_transcribe_audio_sync_with_demucs_writes_temp_and_cleans(monkeypatch, tmp_path):
    """Demucs path: separated vocals written to temp, Whisper called with temp path, temp cleaned."""
    fake_whisper = MagicMock()
    fake_whisper.transcribe.return_value = MagicMock(segments=[], language="en")

    fake_demucs = MagicMock()
    fake_tensor = MagicMock()
    fake_tensor.numpy.return_value.T = "fake_audio_array"
    fake_demucs.separate.return_value = ({"vocals": fake_tensor}, 44100)

    fake_manager = MagicMock()
    fake_manager.gpu_session.return_value.__enter__ = lambda *a: None
    fake_manager.gpu_session.return_value.__exit__ = lambda *a: None
    fake_container = MagicMock(model_manager=lambda: fake_manager)

    monkeypatch.setattr("app.engine.ai.audio.whisper.get_whisper", lambda: fake_whisper)
    monkeypatch.setattr("app.engine.ai.audio.demucs.get_demucs", lambda: fake_demucs)
    monkeypatch.setattr("app.init.container.get_container", lambda: fake_container)

    written_paths: list[str] = []
    def fake_sf_write(path, data, sr):
        written_paths.append(path)
        Path(path).touch()
    monkeypatch.setattr("soundfile.write", fake_sf_write)

    opts = TranscribeOptions(separate_vocals=True, model_size="tiny")
    transcribe_audio_sync(tmp_path / "x.wav", opts)

    assert fake_demucs.separate.called
    assert fake_whisper.transcribe.called
    # Whisper called with a temp vocals path, not the original audio
    call_kwargs = fake_whisper.transcribe.call_args.kwargs
    assert call_kwargs["audio_path"] != tmp_path / "x.wav"
    # Temp file was created and then cleaned up
    assert len(written_paths) == 1
    assert not Path(written_paths[0]).exists()


def test_transcribe_audio_sync_raises_if_demucs_no_vocals(monkeypatch, tmp_path):
    fake_demucs = MagicMock()
    fake_demucs.separate.return_value = ({"other": MagicMock()}, 44100)

    fake_manager = MagicMock()
    fake_manager.gpu_session.return_value.__enter__ = lambda *a: None
    fake_manager.gpu_session.return_value.__exit__ = lambda *a: None
    fake_container = MagicMock(model_manager=lambda: fake_manager)

    monkeypatch.setattr("app.engine.ai.audio.demucs.get_demucs", lambda: fake_demucs)
    monkeypatch.setattr("app.init.container.get_container", lambda: fake_container)

    opts = TranscribeOptions(separate_vocals=True)
    with pytest.raises(RuntimeError, match="vocals"):
        transcribe_audio_sync(tmp_path / "x.wav", opts)


def test_transcribe_audio_sync_with_align_calls_aligner(monkeypatch, tmp_path):
    fake_whisper = MagicMock()
    aligned_segments = [MagicMock(start=0.0, end=1.0, text="aligned")]
    original_segments = [MagicMock(start=0.0, end=1.0, text="original")]
    fake_result = MagicMock(segments=original_segments, language="en")
    fake_whisper.transcribe.return_value = fake_result

    fake_aligner = MagicMock()
    fake_aligner.is_language_supported.return_value = True
    fake_aligner.align.return_value = aligned_segments

    fake_manager = MagicMock()
    fake_manager.gpu_session.return_value.__enter__ = lambda *a: None
    fake_manager.gpu_session.return_value.__exit__ = lambda *a: None
    fake_container = MagicMock(model_manager=lambda: fake_manager)

    monkeypatch.setattr("app.engine.ai.audio.whisper.get_whisper", lambda: fake_whisper)
    monkeypatch.setattr("app.engine.ai.audio.wav2vec2.get_alignment_engine", lambda: fake_aligner)
    monkeypatch.setattr("app.init.container.get_container", lambda: fake_container)

    opts = TranscribeOptions(align=True, model_size="tiny")
    result = transcribe_audio_sync(tmp_path / "x.wav", opts)

    assert fake_aligner.align.called
    assert result.segments == aligned_segments


def test_transcribe_audio_sync_skips_align_if_language_unsupported(monkeypatch, tmp_path):
    fake_whisper = MagicMock()
    segs = [MagicMock()]
    fake_whisper.transcribe.return_value = MagicMock(segments=segs, language="xx")

    fake_aligner = MagicMock()
    fake_aligner.is_language_supported.return_value = False

    fake_manager = MagicMock()
    fake_manager.gpu_session.return_value.__enter__ = lambda *a: None
    fake_manager.gpu_session.return_value.__exit__ = lambda *a: None
    fake_container = MagicMock(model_manager=lambda: fake_manager)

    monkeypatch.setattr("app.engine.ai.audio.whisper.get_whisper", lambda: fake_whisper)
    monkeypatch.setattr("app.engine.ai.audio.wav2vec2.get_alignment_engine", lambda: fake_aligner)
    monkeypatch.setattr("app.init.container.get_container", lambda: fake_container)

    opts = TranscribeOptions(align=True, model_size="tiny")
    result = transcribe_audio_sync(tmp_path / "x.wav", opts)

    fake_aligner.align.assert_not_called()
    assert result.segments == segs
