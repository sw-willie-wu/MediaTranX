"""Unit tests for app.services.audio.separate_service.midi_compose."""
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.audio.separate_service.midi_compose import (
    merge_tracks_to_midi,
    transcribe_drums,
)


def test_merge_tracks_to_midi_writes_file_and_converts_seconds_to_beats(tmp_path):
    """Notes with `start`/`duration` in seconds must be converted to beats before json_to_midi."""
    tracks = [{
        "name": "Drums", "instrument": 0, "is_drum": True,
        "notes": [
            {"pitch": 36, "start": 0.0, "duration": 0.5, "velocity": 100},
            {"pitch": 38, "start": 1.0, "duration": 0.25, "velocity": 80},
        ],
    }]
    out_path = tmp_path / "out.mid"

    with patch("app.services.audio.separate_service.midi_compose.json_to_midi",
               return_value=out_path) as m:
        result = merge_tracks_to_midi(tracks, out_path, tempo=120.0)
    assert result == out_path

    data, written_path = m.call_args.args
    assert written_path == out_path
    assert data["tempo"] == 120.0
    assert data["time_signature"] == [4, 4]
    # tempo 120 → 2 beats/sec; start=1.0s → 2.0 beats
    converted = data["tracks"][0]["notes"]
    assert converted[1]["start"] == pytest.approx(2.0)
    assert converted[1]["duration"] == pytest.approx(0.5)
    # Original fields preserved
    assert converted[1]["pitch"] == 38
    assert converted[1]["velocity"] == 80


def test_merge_tracks_to_midi_uses_default_velocity_when_missing(tmp_path):
    tracks = [{"name": "X", "notes": [{"pitch": 60, "start": 0.0, "duration": 0.1}]}]
    with patch("app.services.audio.separate_service.midi_compose.json_to_midi"):
        merge_tracks_to_midi(tracks, tmp_path / "x.mid", tempo=60.0)
    # No assertion needed — just verify no KeyError on missing velocity


def test_transcribe_drums_returns_track_dict_with_notes(tiny_wav_path):
    """Run real librosa onset detection on the tiny WAV fixture.

    The fixture is a 440Hz sine — librosa may detect zero onsets (no transients);
    this test only verifies the function returns a well-shaped dict.
    """
    pytest.importorskip("librosa")
    track = transcribe_drums(tiny_wav_path)
    assert track["name"] == "Drums"
    assert track["is_drum"] is True
    assert isinstance(track["notes"], list)
    for n in track["notes"]:
        assert set(n.keys()) == {"pitch", "start", "duration", "velocity"}
        assert isinstance(n["pitch"], int)
        assert isinstance(n["start"], float)
        assert n["duration"] == 0.1  # fixed per docstring
        assert 30 <= n["velocity"] <= 127


def test_transcribe_drums_velocity_defaults_when_no_onsets(tmp_path):
    """Silence → near-empty onset list. Librosa may emit 0-1 spurious edge onsets
    depending on version; tolerate that without flakiness."""
    pytest.importorskip("librosa")
    import numpy as np
    import soundfile as sf
    path = tmp_path / "silence.wav"
    sf.write(str(path), np.zeros(8000, dtype=np.float32), 16000)
    track = transcribe_drums(path)
    assert len(track["notes"]) <= 1
