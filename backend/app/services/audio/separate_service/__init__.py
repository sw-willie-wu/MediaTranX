"""Audio source separation feature subpackage.

Public entry point: AudioSeparateService. Drum MIDI composition
helpers live in `midi_compose.py`.
"""
from .service import AudioSeparateService

__all__ = ["AudioSeparateService"]
