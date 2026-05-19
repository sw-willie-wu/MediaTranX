"""Tests for app.utils.midi_io — MIDI file ↔ JSON helpers."""
from __future__ import annotations
from pathlib import Path

import pytest

from app.utils.midi_io import (
    midi_to_json,
    json_to_midi,
    _bpm_from_tempo,
    _tempo_from_bpm,
    _TRACK_COLORS,
)


class TestBpmTempoRoundTrip:
    @pytest.mark.parametrize("bpm", [60.0, 90.0, 120.0, 140.0, 240.0])
    def test_round_trip(self, bpm):
        tempo = _tempo_from_bpm(bpm)
        recovered = _bpm_from_tempo(tempo)
        assert recovered == pytest.approx(bpm, abs=0.01)

    def test_120bpm_is_default_500000us(self):
        assert _tempo_from_bpm(120.0) == 500_000
        assert _bpm_from_tempo(500_000) == pytest.approx(120.0)


def _write_minimal_midi(path: Path, tempo_us=500_000, time_sig=(4, 4)) -> Path:
    """Write a minimal 1-track MIDI file (no notes) with tempo + time signature."""
    import mido

    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))
    track.append(mido.MetaMessage(
        "time_signature", numerator=time_sig[0], denominator=time_sig[1], time=0,
    ))
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(track)
    mid.save(str(path))
    return path


def _write_midi_with_one_note(path: Path) -> Path:
    """Single-track MIDI: program_change(piano) + middle C note (480 ticks = 1 beat)."""
    import mido

    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
    track.append(mido.MetaMessage("track_name", name="Piano", time=0))
    track.append(mido.Message("program_change", program=0, channel=0, time=0))
    track.append(mido.Message("note_on", note=60, velocity=80, channel=0, time=0))
    track.append(mido.Message("note_off", note=60, velocity=0, channel=0, time=480))
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(track)
    mid.save(str(path))
    return path


class TestMidiToJsonBasics:
    def test_empty_file_returns_no_tracks(self, tmp_path):
        path = _write_minimal_midi(tmp_path / "empty.mid")
        result = midi_to_json(path)
        assert result["ticks_per_beat"] == 480
        assert result["tempo"] == pytest.approx(120.0)
        assert result["time_signature"] == [4, 4]
        assert result["tracks"] == []

    def test_tempo_extraction(self, tmp_path):
        path = _write_minimal_midi(tmp_path / "tempo.mid", tempo_us=375_000)  # 160 bpm
        result = midi_to_json(path)
        assert result["tempo"] == pytest.approx(160.0)

    def test_time_signature_extraction(self, tmp_path):
        path = _write_minimal_midi(tmp_path / "ts.mid", time_sig=(7, 8))
        result = midi_to_json(path)
        assert result["time_signature"] == [7, 8]

    def test_single_note_track(self, tmp_path):
        path = _write_midi_with_one_note(tmp_path / "note.mid")
        result = midi_to_json(path)
        assert len(result["tracks"]) == 1
        track = result["tracks"][0]
        assert track["name"] == "Piano"
        assert track["instrument"] == 0
        assert track["is_drum"] is False
        assert len(track["notes"]) == 1
        note = track["notes"][0]
        assert note["pitch"] == 60
        assert note["start"] == pytest.approx(0.0)
        assert note["duration"] == pytest.approx(1.0)  # 480 ticks / 480 tpb = 1 beat
        assert note["velocity"] == 80

    def test_track_color_assigned(self, tmp_path):
        path = _write_midi_with_one_note(tmp_path / "color.mid")
        result = midi_to_json(path)
        assert result["tracks"][0]["color"] in _TRACK_COLORS


class TestDrumDetection:
    def test_channel_9_is_drum(self, tmp_path):
        import mido
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        track.append(mido.Message("program_change", program=0, channel=9, time=0))
        track.append(mido.Message("note_on", note=36, velocity=100, channel=9, time=0))
        track.append(mido.Message("note_off", note=36, velocity=0, channel=9, time=240))
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)
        path = tmp_path / "drum.mid"
        mid.save(str(path))
        result = midi_to_json(path)
        assert result["tracks"][0]["is_drum"] is True

    def test_track_name_heuristic(self, tmp_path):
        """Track named 'drums' should be flagged is_drum even on non-9 channel."""
        import mido
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name="Drums", time=0))
        track.append(mido.Message("program_change", program=0, channel=0, time=0))
        track.append(mido.Message("note_on", note=36, velocity=100, channel=0, time=0))
        track.append(mido.Message("note_off", note=36, velocity=0, channel=0, time=240))
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)
        path = tmp_path / "named_drums.mid"
        mid.save(str(path))
        result = midi_to_json(path)
        assert result["tracks"][0]["is_drum"] is True


class TestDanglingNoteOn:
    def test_note_on_without_off_gets_1beat_duration(self, tmp_path):
        import mido
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        track.append(mido.Message("note_on", note=72, velocity=100, channel=0, time=0))
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)
        path = tmp_path / "dangling.mid"
        mid.save(str(path))
        result = midi_to_json(path)
        assert len(result["tracks"]) == 1
        notes = result["tracks"][0]["notes"]
        assert len(notes) == 1
        assert notes[0]["pitch"] == 72
        assert notes[0]["duration"] == pytest.approx(1.0)


class TestJsonToMidi:
    def test_writes_file_to_path(self, tmp_path):
        data = {"ticks_per_beat": 480, "tempo": 120.0, "tracks": []}
        out = json_to_midi(data, tmp_path / "out.mid")
        assert out.exists()
        assert out.suffix == ".mid"

    def test_creates_parent_dirs(self, tmp_path):
        data = {"ticks_per_beat": 480, "tempo": 120.0, "tracks": []}
        out = json_to_midi(data, tmp_path / "nested" / "deep" / "out.mid")
        assert out.exists()

    def test_drum_track_uses_channel_9(self, tmp_path):
        """is_drum=True tracks should be written on channel 9."""
        import mido
        data = {
            "ticks_per_beat": 480,
            "tempo": 120.0,
            "time_signature": [4, 4],
            "tracks": [{
                "name": "Drum Kit",
                "instrument": 0,
                "is_drum": True,
                "notes": [{"pitch": 36, "start": 0.0, "duration": 0.5, "velocity": 100}],
            }],
        }
        out = json_to_midi(data, tmp_path / "drum.mid")
        mid = mido.MidiFile(str(out))
        # Find note_on; channel should be 9
        for tk in mid.tracks:
            for msg in tk:
                if msg.type == "note_on" and msg.velocity > 0:
                    assert msg.channel == 9
                    return
        pytest.fail("No note_on message found in written drum track")

    def test_non_drum_skips_channel_9(self, tmp_path):
        """Non-drum tracks get channels 0,1,2,...8,10,11,... — never 9."""
        import mido
        data = {
            "ticks_per_beat": 480,
            "tempo": 120.0,
            "tracks": [
                {"name": f"T{i}", "instrument": 0, "is_drum": False,
                 "notes": [{"pitch": 60 + i, "start": 0.0, "duration": 0.25, "velocity": 80}]}
                for i in range(10)  # 10 tracks → spans channels 0,1,...,8,10
            ],
        }
        out = json_to_midi(data, tmp_path / "many.mid")
        mid = mido.MidiFile(str(out))
        channels_seen: set[int] = set()
        for tk in mid.tracks:
            for msg in tk:
                if msg.type == "note_on" and msg.velocity > 0:
                    channels_seen.add(msg.channel)
        assert 9 not in channels_seen
        # 10 non-drum tracks → spans 0..8 then jumps to 10
        assert {0, 1, 2, 3, 4, 5, 6, 7, 8, 10}.issubset(channels_seen)

    def test_note_timing_beat_to_tick(self, tmp_path):
        """note start=1.0 beats + duration=2.0 beats → ticks 480, 480 (1 to 3 beats)."""
        import mido
        data = {
            "ticks_per_beat": 480,
            "tempo": 120.0,
            "tracks": [{
                "name": "T", "instrument": 0, "is_drum": False,
                "notes": [{"pitch": 60, "start": 1.0, "duration": 2.0, "velocity": 80}],
            }],
        }
        out = json_to_midi(data, tmp_path / "timing.mid")
        mid = mido.MidiFile(str(out))
        # Walk events; find note_on and note_off absolute ticks
        for tk in mid.tracks:
            abs_tick = 0
            note_on_tick = None
            note_off_tick = None
            for msg in tk:
                abs_tick += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    note_on_tick = abs_tick
                elif msg.type == "note_off":
                    note_off_tick = abs_tick
            if note_on_tick is not None:
                assert note_on_tick == 480  # 1 beat × 480 tpb
                assert note_off_tick - note_on_tick == 960  # 2 beats × 480 tpb
                return
        pytest.fail("No note events found")


class TestRoundTrip:
    def test_single_note_roundtrip_preserves_pitch_duration(self, tmp_path):
        """midi_to_json → json_to_midi → midi_to_json should preserve note data."""
        src = _write_midi_with_one_note(tmp_path / "src.mid")
        json_a = midi_to_json(src)

        roundtrip_path = tmp_path / "rt.mid"
        json_to_midi(json_a, roundtrip_path)
        json_b = midi_to_json(roundtrip_path)

        assert json_b["ticks_per_beat"] == json_a["ticks_per_beat"]
        assert json_b["tempo"] == pytest.approx(json_a["tempo"])
        assert len(json_b["tracks"]) == len(json_a["tracks"]) == 1
        n_a = json_a["tracks"][0]["notes"][0]
        n_b = json_b["tracks"][0]["notes"][0]
        assert n_a["pitch"] == n_b["pitch"]
        assert n_a["start"] == pytest.approx(n_b["start"])
        assert n_a["duration"] == pytest.approx(n_b["duration"])
        assert n_a["velocity"] == n_b["velocity"]
