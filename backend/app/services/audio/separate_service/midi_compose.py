"""Drum MIDI composition helpers for AudioSeparateService.

- transcribe_drums: librosa onset detection → drum note dict
- merge_tracks_to_midi: merge dicts into a single .mid, delegating to json_to_midi
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from app.utils.midi_io import json_to_midi

logger = logging.getLogger(__name__)


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


def transcribe_drums(audio_path: str | Path, sr: int = 44100) -> dict[str, Any]:
    """Simple spectral drum transcription for a clean drum stem.

    Returns a track dict with note ``start`` values in **seconds** and a fixed
    ``duration`` of 0.1 s (drum hits are treated as instantaneous).

    Uses ``librosa`` for onset detection and ``numpy`` for spectral analysis.
    """
    import librosa

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
