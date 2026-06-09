from unittest.mock import patch

from app.schemas.compute_settings import ComputeSettings, ComputeSettingsUpdate
from app.services.setup.compute_settings_service import ComputeSettingsService


def test_compute_settings_defaults_allow_true():
    assert ComputeSettings().allow_cpu_fallback is True


def test_compute_settings_update_is_optional():
    assert ComputeSettingsUpdate().allow_cpu_fallback is None
    assert ComputeSettingsUpdate(allow_cpu_fallback=False).allow_cpu_fallback is False


def test_get_settings_defaults_on_when_absent():
    svc = ComputeSettingsService()
    with patch.object(svc._dao, "get", return_value=None):
        assert svc.get_settings().allow_cpu_fallback is True


def test_update_persists_and_pushes_policy():
    svc = ComputeSettingsService()
    with patch.object(svc._dao, "get", return_value={"allow_cpu_fallback": True}), \
         patch.object(svc._dao, "set") as mock_set, \
         patch("app.adapters.device.set_allow_cpu_fallback") as mock_policy:
        out = svc.update_settings({"allow_cpu_fallback": False})
    assert out.allow_cpu_fallback is False
    mock_set.assert_called_once_with("compute", {"allow_cpu_fallback": False})
    mock_policy.assert_called_once_with(False)
