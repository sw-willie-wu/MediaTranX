"""Compute-policy settings service (GPU→CPU fallback toggle).

DB-backed via AppSettingDAO (live, no restart). On update it pushes the policy
into the device module so the change takes effect for the next task immediately.
Mirrors VideoDownloadService (backend/app/services/video/download_service.py).
"""
import logging

from app.adapters import device
from app.db.dao.app_setting_dao import AppSettingDAO
from app.schemas.compute_settings import ComputeSettings

logger = logging.getLogger(__name__)

SETTINGS_KEY = "compute"


class ComputeSettingsService:
    def __init__(self):
        self._dao = AppSettingDAO()  # internal, mirrors VideoDownloadService (not DI)
        logger.info("ComputeSettingsService initialized")

    def get_settings(self) -> ComputeSettings:
        raw = self._dao.get(SETTINGS_KEY) or {}
        return ComputeSettings.model_validate(raw)

    def update_settings(self, patch: dict) -> ComputeSettings:
        current = self.get_settings().model_dump()
        for key, value in patch.items():
            if value is not None:
                current[key] = value
        merged = ComputeSettings.model_validate(current)
        self._dao.set(SETTINGS_KEY, merged.model_dump())
        device.set_allow_cpu_fallback(merged.allow_cpu_fallback)
        return merged
