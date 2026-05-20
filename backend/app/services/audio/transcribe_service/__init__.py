"""Audio transcribe feature subpackage.

Public entry point: AudioTranscribeService. Map-reduce summarization
helper (single consumer — this service's `_execute`) lives in `summarize.py`.
"""
from .service import AudioTranscribeService

__all__ = ["AudioTranscribeService"]
