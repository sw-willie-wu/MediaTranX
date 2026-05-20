"""
MIDI JSON I/O helpers (file ↔ JSON). Shared by audio_midi_service (editing
and round-trip) and separate_service's drum merge path.

All heavy external packages (mido) are lazy-imported inside functions to
comply with the project lazy-import rule.
"""
from __future__ import annotations

import logging
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
