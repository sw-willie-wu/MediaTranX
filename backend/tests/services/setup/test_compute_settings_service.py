from app.schemas.compute_settings import ComputeSettings, ComputeSettingsUpdate


def test_compute_settings_defaults_allow_true():
    assert ComputeSettings().allow_cpu_fallback is True


def test_compute_settings_update_is_optional():
    assert ComputeSettingsUpdate().allow_cpu_fallback is None
    assert ComputeSettingsUpdate(allow_cpu_fallback=False).allow_cpu_fallback is False
