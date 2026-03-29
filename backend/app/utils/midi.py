"""
MIDI utilities — JSON conversion, multi-track merge, and drum transcription.

All heavy external packages (mido, librosa, numpy) are lazy-imported inside
functions to comply with the project lazy-import rule.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Rotating colour palette for track visualisation (12 colours).
_TRACK_COLORS = [
    "#4FC3F7",  # light blue
    "#81C784",  # green
    "#FFB74D",  # orange
    "#E57373",  # red
    "#BA68C8",  # purple
    "#4DB6AC",  # teal
    "#FFD54F",  # amber
    "#F06292",  # pink
    "#AED581",  # light green
    "#64B5F6",  # blue
    "#FF8A65",  # deep orange
    "#9575CD",  # deep purple
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _bpm_from_tempo(tempo_us: int) -> float:
    """Convert MIDI tempo (microseconds per beat) to BPM."""
    return 60_000_000.0 / tempo_us


def _tempo_from_bpm(bpm: float) -> int:
    """Convert BPM to MIDI tempo (microseconds per beat)."""
    return round(60_000_000.0 / bpm)


# ── 1. midi_to_json ─────────────────────────────────────────────────────────

def midi_to_json(midi_path: str | Path) -> dict[str, Any]:
    """Read a *.mid* file and return a canonical JSON-serialisable dict.

    Timing values (``start``, ``duration``) are expressed in **beats**
    (ticks divided by *ticks_per_beat*).
    """
    import mido

    midi_path = Path(midi_path)
    mid = mido.MidiFile(str(midi_path))

    tpb: int = mid.ticks_per_beat

    # --- global meta: tempo & time signature (from first occurrences) -------
    tempo_us: int = 500_000  # default 120 BPM
    time_sig: list[int] = [4, 4]

    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                tempo_us = msg.tempo
                break
            if msg.type == "time_signature":
                time_sig = [msg.numerator, msg.denominator]
                break

    # second pass in case time_signature was in a different track
    for track in mid.tracks:
        for msg in track:
            if msg.type == "time_signature":
                time_sig = [msg.numerator, msg.denominator]
                break

    bpm = _bpm_from_tempo(tempo_us)

    # --- per-track parsing ---------------------------------------------------
    tracks_out: list[dict[str, Any]] = []
    color_idx = 0

    for track in mid.tracks:
        track_name: str = ""
        instrument: int = 0
        volume: int = 100
        pan: int = 64
        is_drum = False
        notes: list[dict[str, Any]] = []
        pending: dict[tuple[int, int], list[tuple[int, int]]] = {}
        # pending: (channel, pitch) -> [(tick_on, velocity), ...]

        abs_tick = 0
        for msg in track:
            abs_tick += msg.time

            if msg.type == "track_name":
                track_name = msg.name

            elif msg.type == "program_change":
                instrument = msg.program
                if msg.channel == 9:
                    is_drum = True

            elif msg.type == "control_change":
                if msg.control == 7:
                    volume = msg.value
                elif msg.control == 10:
                    pan = msg.value

            elif msg.type == "note_on" and msg.velocity > 0:
                if msg.channel == 9:
                    is_drum = True
                key = (msg.channel, msg.note)
                pending.setdefault(key, []).append((abs_tick, msg.velocity))

            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                key = (msg.channel, msg.note)
                if key in pending and pending[key]:
                    tick_on, vel = pending[key].pop(0)
                    dur_ticks = abs_tick - tick_on
                    notes.append(
                        {
                            "pitch": msg.note,
                            "start": tick_on / tpb,
                            "duration": max(dur_ticks / tpb, 1 / tpb),
                            "velocity": vel,
                        }
                    )
                    if not pending[key]:
                        del pending[key]

        # flush any dangling note-on (give them 1-beat duration)
        for (ch, pitch), onsets in pending.items():
            for tick_on, vel in onsets:
                notes.append(
                    {
                        "pitch": pitch,
                        "start": tick_on / tpb,
                        "duration": 1.0,
                        "velocity": vel,
                    }
                )

        if not notes:
            continue

        # drum heuristic: track name contains "drum"
        if not is_drum and "drum" in track_name.lower():
            is_drum = True

        notes.sort(key=lambda n: (n["start"], n["pitch"]))

        tracks_out.append(
            {
                "name": track_name or f"Track {len(tracks_out) + 1}",
                "instrument": instrument,
                "color": _TRACK_COLORS[color_idx % len(_TRACK_COLORS)],
                "volume": volume,
                "pan": pan,
                "muted": False,
                "is_drum": is_drum,
                "notes": notes,
            }
        )
        color_idx += 1

    return {
        "ticks_per_beat": tpb,
        "tempo": round(bpm, 2),
        "time_signature": time_sig,
        "tracks": tracks_out,
    }


# ── 2. json_to_midi ─────────────────────────────────────────────────────────

def json_to_midi(data: dict[str, Any], output_path: str | Path) -> Path:
    """Write the canonical JSON dict back to a *.mid* file.

    ``start`` and ``duration`` in the JSON are in **beats**; they are converted
    to ticks via *ticks_per_beat*.
    """
    import mido

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tpb: int = data.get("ticks_per_beat", 480)
    bpm: float = data.get("tempo", 120.0)
    ts: list[int] = data.get("time_signature", [4, 4])
    tempo_us = _tempo_from_bpm(bpm)

    mid = mido.MidiFile(ticks_per_beat=tpb)

    # --- tempo / meta track --------------------------------------------------
    meta_track = mido.MidiTrack()
    meta_track.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))
    meta_track.append(
        mido.MetaMessage(
            "time_signature",
            numerator=ts[0],
            denominator=ts[1],
            time=0,
        )
    )
    meta_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(meta_track)

    # --- channel allocation (skip 9 for non-drum) ----------------------------
    non_drum_channels = [c for c in range(16) if c != 9]
    ch_idx = 0

    for trk_data in data.get("tracks", []):
        is_drum: bool = trk_data.get("is_drum", False)
        if is_drum:
            channel = 9
        else:
            channel = non_drum_channels[ch_idx % len(non_drum_channels)]
            ch_idx += 1

        midi_track = mido.MidiTrack()

        # track name
        name = trk_data.get("name", "")
        if name:
            midi_track.append(mido.MetaMessage("track_name", name=name, time=0))

        # program change
        instrument = trk_data.get("instrument", 0)
        midi_track.append(
            mido.Message("program_change", channel=channel, program=instrument, time=0)
        )

        # volume / pan
        volume = trk_data.get("volume", 100)
        pan = trk_data.get("pan", 64)
        midi_track.append(
            mido.Message("control_change", channel=channel, control=7, value=volume, time=0)
        )
        midi_track.append(
            mido.Message("control_change", channel=channel, control=10, value=pan, time=0)
        )

        # --- build absolute-tick events, then convert to delta ----------------
        events: list[tuple[int, mido.Message]] = []

        for note in trk_data.get("notes", []):
            pitch = int(note["pitch"])
            vel = int(note.get("velocity", 80))
            start_tick = round(note["start"] * tpb)
            dur_tick = max(round(note["duration"] * tpb), 1)

            events.append(
                (
                    start_tick,
                    mido.Message(
                        "note_on", channel=channel, note=pitch, velocity=vel, time=0
                    ),
                )
            )
            events.append(
                (
                    start_tick + dur_tick,
                    mido.Message(
                        "note_off", channel=channel, note=pitch, velocity=0, time=0
                    ),
                )
            )

        # sort by absolute tick; for ties note_off before note_on
        events.sort(key=lambda e: (e[0], 0 if e[1].type == "note_off" else 1))

        prev_tick = 0
        for abs_tick, msg in events:
            msg.time = abs_tick - prev_tick
            midi_track.append(msg)
            prev_tick = abs_tick

        midi_track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(midi_track)

    mid.save(str(output_path))
    logger.info("Wrote MIDI: %s", output_path)
    return output_path


# ── 3. merge_tracks_to_midi ─────────────────────────────────────────────────

def merge_tracks_to_midi(
    tracks: list[dict[str, Any]],
    output_path: str | Path,
    tempo: float = 120.0,
    ticks_per_beat: int = 480,
) -> Path:
    """Merge several track dicts into a single *.mid* file.

    Input notes have ``start`` / ``duration`` in **seconds**; they are
    converted to **beats** before delegating to :func:`json_to_midi`.
    """
    beats_per_sec = tempo / 60.0

    converted_tracks: list[dict[str, Any]] = []
    for trk in tracks:
        new_notes: list[dict[str, Any]] = []
        for n in trk.get("notes", []):
            new_notes.append(
                {
                    "pitch": n["pitch"],
                    "start": n["start"] * beats_per_sec,
                    "duration": n["duration"] * beats_per_sec,
                    "velocity": n.get("velocity", 80),
                }
            )
        converted_tracks.append({**trk, "notes": new_notes})

    data: dict[str, Any] = {
        "ticks_per_beat": ticks_per_beat,
        "tempo": tempo,
        "time_signature": [4, 4],
        "tracks": converted_tracks,
    }
    return json_to_midi(data, output_path)


# ── 4. transcribe_drums ─────────────────────────────────────────────────────

def transcribe_drums(audio_path: str | Path, sr: int = 44100) -> dict[str, Any]:
    """Simple spectral drum transcription for a clean drum stem.

    Returns a track dict with note ``start`` values in **seconds** and a fixed
    ``duration`` of 0.1 s (drum hits are treated as instantaneous).

    Uses ``librosa`` for onset detection and ``numpy`` for spectral analysis.
    """
    import librosa
    import numpy as np

    audio_path = Path(audio_path)
    y, sr = librosa.load(str(audio_path), sr=sr, mono=True)

    # --- onset detection -----------------------------------------------------
    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr, backtrack=True, units="frames",
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    onset_samples = librosa.frames_to_samples(onset_frames)

    # --- velocity estimation -------------------------------------------------
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    # map each onset frame to strength, then normalise to 30-127
    raw_strengths = onset_env[onset_frames] if len(onset_frames) > 0 else np.array([])
    if len(raw_strengths) > 0:
        s_min = raw_strengths.min()
        s_max = raw_strengths.max()
        if s_max - s_min > 0:
            velocities = 30 + (raw_strengths - s_min) / (s_max - s_min) * 97
        else:
            velocities = np.full_like(raw_strengths, 80.0)
        velocities = np.clip(velocities, 30, 127).astype(int)
    else:
        velocities = np.array([], dtype=int)

    # --- spectral classification per onset -----------------------------------
    hop = librosa.samples_to_frames(1, hop_length=512)  # not used directly
    window_samples = int(0.05 * sr)  # 50 ms window

    notes: list[dict[str, Any]] = []

    for i, sample_pos in enumerate(onset_samples):
        start_s = int(max(sample_pos - window_samples // 2, 0))
        end_s = int(min(sample_pos + window_samples // 2, len(y)))
        segment = y[start_s:end_s]

        if len(segment) < 64:
            # too short for meaningful analysis – default to snare
            notes.append(
                {"pitch": 38, "start": float(onset_times[i]),
                 "duration": 0.1, "velocity": int(velocities[i])}
            )
            continue

        # FFT
        n_fft = len(segment)
        spectrum = np.abs(np.fft.rfft(segment, n=n_fft))
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)

        total_energy = float(np.sum(spectrum ** 2))
        if total_energy == 0:
            total_energy = 1e-10

        low_mask = freqs < 200
        mid_mask = (freqs >= 200) & (freqs <= 5000)
        high_mask = freqs > 5000

        low_energy = float(np.sum(spectrum[low_mask] ** 2)) / total_energy
        mid_energy = float(np.sum(spectrum[mid_mask] ** 2)) / total_energy
        high_energy = float(np.sum(spectrum[high_mask] ** 2)) / total_energy

        # spectral centroid
        if np.sum(spectrum) > 0:
            centroid = float(np.sum(freqs * spectrum) / np.sum(spectrum))
        else:
            centroid = 1000.0

        # decay estimation for crash vs hi-hat
        # compare energy in 1st half vs 2nd half of the segment
        half = len(segment) // 2
        energy_first = float(np.sum(segment[:half] ** 2))
        energy_second = float(np.sum(segment[half:] ** 2))
        slow_decay = energy_second > 0.3 * energy_first if energy_first > 0 else False

        # classification
        if centroid < 300 and low_energy > 0.5:
            pitch = 36  # Kick
        elif 300 <= centroid < 3000 and low_energy > 0.3:
            pitch = 47  # Tom
        elif 300 <= centroid < 3000:
            pitch = 38  # Snare
        elif high_energy > 0.4 and slow_decay:
            pitch = 49  # Crash
        elif high_energy > 0.4:
            pitch = 42  # Hi-hat closed
        else:
            pitch = 38  # Snare (default)

        notes.append(
            {
                "pitch": pitch,
                "start": float(onset_times[i]),
                "duration": 0.1,
                "velocity": int(velocities[i]),
            }
        )

    logger.info(
        "Drum transcription: %d onsets detected in %s", len(notes), audio_path.name,
    )

    return {
        "name": "Drums",
        "instrument": 0,
        "is_drum": True,
        "notes": notes,
    }
