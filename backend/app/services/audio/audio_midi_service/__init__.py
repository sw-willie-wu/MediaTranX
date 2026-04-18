"""Audio MIDI editing feature subpackage.

Public entry point: AudioMidiService. MIDI I/O helpers live in
`app.utils.midi_io` (shared with the separate service's merge path).
"""
from .service import AudioMidiService

__all__ = ["AudioMidiService"]
