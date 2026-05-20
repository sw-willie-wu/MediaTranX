"""AI model wrapper family.

Wrapper classes are imported directly from their specific modules
(e.g. `from .whisper import WhisperWrapper`). Singleton lifecycle and
per-slot dispatch are owned by the DI container (see `app/init/container.py`)
and `ModelManager` (see `app/adapters/ai/model_manager.py`).
"""
