"""
FluidSynth wrapper — SoundFont-based MIDI rendering.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from app.engine.paths import get_fluidsynth_dir

logger = logging.getLogger(__name__)

import sys as _sys

SF2_FILENAME = "FluidR3_GM.sf2"
DLL_FILENAME = "libfluidsynth-3.dll" if _sys.platform == "win32" else "libfluidsynth.so"


class FluidSynthWrapper:
    """SoundFont loading/unloading and MIDI→WAV rendering."""

    def __init__(self):
        self._dir = get_fluidsynth_dir()

    @property
    def sf2_path(self) -> Path:
        return self._dir / SF2_FILENAME

    @property
    def dll_path(self) -> Path:
        return self._dir / DLL_FILENAME

    def is_available(self) -> dict:
        """Check availability of FluidSynth library and SoundFont."""
        if _sys.platform == "win32":
            dll_ok = self.dll_path.exists()
        else:
            # Linux/macOS: check system libfluidsynth or bundled
            import shutil
            dll_ok = self.dll_path.exists() or shutil.which("fluidsynth") is not None
        sf2_ok = self.sf2_path.exists()
        return {
            "dll_available": dll_ok,
            "sf2_available": sf2_ok,
            "ready": dll_ok and sf2_ok,
        }

    def render_midi_to_wav(
        self,
        midi_path: str | Path,
        output_path: str | Path,
        sample_rate: int = 44100,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        """Render a .mid file to .wav using FluidSynth + SoundFont.

        Uses midi2audio for simplicity (wraps fluidsynth CLI-style).
        Falls back to pyfluidsynth direct API if midi2audio unavailable.
        """
        status = self.is_available()
        if not status["ready"]:
            missing = []
            if not status["dll_available"]:
                missing.append("libfluidsynth DLL")
            if not status["sf2_available"]:
                missing.append("SoundFont (FluidR3_GM.sf2)")
            raise FileNotFoundError(
                f"FluidSynth not ready. Missing: {', '.join(missing)}. "
                "Please download via Settings → Model Management."
            )

        if on_progress:
            on_progress(0.1, "Loading SoundFont...")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Ensure pyfluidsynth can find our bundled DLL
        import os, sys
        dll_dir = str(self._dir)
        if sys.platform == "win32":
            os.add_dll_directory(dll_dir)
        if dll_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")

        import fluidsynth
        import numpy as np
        import soundfile as sf

        if on_progress:
            on_progress(0.2, "Initializing synthesizer...")

        synth = fluidsynth.Synth(samplerate=float(sample_rate))
        sf_id = synth.sfload(str(self.sf2_path))
        synth.program_select(0, sf_id, 0, 0)

        if on_progress:
            on_progress(0.3, "Rendering MIDI...")

        # Read MIDI and render note by note
        import mido

        mid = mido.MidiFile(str(midi_path))
        total_time = mid.length  # total duration in seconds

        # Allocate buffer for entire duration + 2s tail
        total_samples = int((total_time + 2.0) * sample_rate)
        audio_buffer = np.zeros((total_samples, 2), dtype=np.float32)

        # Process all MIDI events
        current_sample = 0
        for msg in mid:
            if msg.time > 0:
                # Render samples for this time gap
                samples_needed = int(msg.time * sample_rate)
                if samples_needed > 0 and current_sample < total_samples:
                    chunk = synth.get_samples(samples_needed)
                    # get_samples returns interleaved stereo as numpy array
                    chunk = chunk.reshape(-1, 2)
                    end = min(current_sample + len(chunk), total_samples)
                    audio_buffer[current_sample:end] = chunk[:end - current_sample] / 32768.0
                    current_sample = end

            if on_progress and current_sample > 0:
                progress = 0.3 + (current_sample / total_samples) * 0.5
                on_progress(min(0.8, progress), "Rendering...")

            # Send MIDI message to synth
            if msg.type == 'note_on':
                synth.noteon(msg.channel, msg.note, msg.velocity)
            elif msg.type == 'note_off':
                synth.noteoff(msg.channel, msg.note)
            elif msg.type == 'program_change':
                synth.program_select(msg.channel, sf_id, 0, msg.program)
            elif msg.type == 'control_change':
                synth.cc(msg.channel, msg.control, msg.value)

        # Render remaining tail (release/reverb)
        tail_samples = min(2 * sample_rate, total_samples - current_sample)
        if tail_samples > 0:
            chunk = synth.get_samples(tail_samples)
            chunk = chunk.reshape(-1, 2)
            end = min(current_sample + len(chunk), total_samples)
            audio_buffer[current_sample:end] = chunk[:end - current_sample] / 32768.0

        synth.delete()

        if on_progress:
            on_progress(0.9, "Writing WAV...")

        # Trim trailing silence
        max_amp = np.max(np.abs(audio_buffer), axis=1)
        last_nonsilent = np.where(max_amp > 0.001)[0]
        if len(last_nonsilent) > 0:
            audio_buffer = audio_buffer[:last_nonsilent[-1] + sample_rate]  # +1s after last sound

        sf.write(str(out), audio_buffer, sample_rate)

        if on_progress:
            on_progress(1.0, "Rendering complete")

        logger.info(f"MIDI rendered to WAV: {out}")
        return out


# Singleton
_fluidsynth: Optional[FluidSynthWrapper] = None


def get_fluidsynth() -> FluidSynthWrapper:
    global _fluidsynth
    if _fluidsynth is None:
        _fluidsynth = FluidSynthWrapper()
    return _fluidsynth
