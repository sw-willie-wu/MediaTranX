"""Ollama inference-settings service (num_ctx cap).

DB-backed via AppSettingDAO (live, no restart). On update it pushes the cap
into the ollama adapter module so the next chat request uses it immediately.
Mirrors ComputeSettingsService.
"""
import logging
import os

from app.db.dao.app_setting_dao import AppSettingDAO
from app.schemas.ollama_settings import _NUM_CTX_MAX, _NUM_CTX_MIN, OllamaSettings

logger = logging.getLogger(__name__)

SETTINGS_KEY = "ollama"


def _env_default() -> int:
    """env MTX_OLLAMA_MAX_NUM_CTX (or 8192) — the fallback when DB has no value,
    preserving existing back-compat. Clamped to [MIN, MAX] so a pre-existing
    out-of-range env value (e.g. 100 or 200000) can't raise ValidationError in
    apply_persisted (which lifespan's try/except would swallow, leaving the
    import-time out-of-range value in place)."""
    try:
        v = int(os.environ.get("MTX_OLLAMA_MAX_NUM_CTX", "8192"))
    except ValueError:
        return 8192
    return max(_NUM_CTX_MIN, min(v, _NUM_CTX_MAX))


class OllamaSettingsService:
    def __init__(self):
        self._dao = AppSettingDAO()  # internal, mirrors ComputeSettingsService (not DI)
        logger.info("OllamaSettingsService initialized")

    def get_settings(self) -> OllamaSettings:
        raw = self._dao.get(SETTINGS_KEY) or {}
        if "ollama_num_ctx_cap" not in raw:        # DAO None/{} or row missing the key
            raw = {**raw, "ollama_num_ctx_cap": _env_default()}  # → env (clamped) / 8192
        return OllamaSettings.model_validate(raw)

    def update_settings(self, patch: dict) -> OllamaSettings:
        from app.adapters.ai.remote import ollama  # lazy: keep ollama.py out of eager import graph
        current = self.get_settings().model_dump()
        for key, value in patch.items():
            if value is not None:
                current[key] = value
        merged = OllamaSettings.model_validate(current)  # triggers ge/le bounds (out-of-range → 422)
        self._dao.set(SETTINGS_KEY, merged.model_dump())
        ollama.set_num_ctx_cap(merged.ollama_num_ctx_cap)  # live-apply
        return merged

    def apply_persisted(self) -> None:
        """Startup: push the persisted (or env-clamped) value into the ollama module."""
        from app.adapters.ai.remote import ollama  # lazy
        ollama.set_num_ctx_cap(self.get_settings().ollama_num_ctx_cap)
