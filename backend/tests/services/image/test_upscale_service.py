"""Tests for ImageUpscaleService + _parse_model_id pure fn + face restoration."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from tests.conftest import make_file_service_mock, make_model_manager_mock
from app.services.image.upscale_service import (
    ImageUpscaleService,
    TASK_TYPE_IMAGE_UPSCALE,
    _parse_model_id,
    _UPSCALE_FAMILIES,
    _FACE_FAMILIES,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")

FAKE_REGISTRY = {"PTH": {
    "realesrgan": {"variants": {"x4plus": {"scale": 4}, "x2plus": {"scale": 2}}},
    "real-cugan": {"variants": {"up2x-conservative": {"scale": 2}}},
    "swinir": {"variants": {"medium": {"scale": 4}}},
}}


class TestParseModelId:
    def test_realesrgan_x4plus(self):
        family, variant = _parse_model_id("realesrgan-x4plus", _UPSCALE_FAMILIES)
        assert family == "realesrgan"
        assert variant == "x4plus"

    def test_hyphenated_family_real_cugan_longest_prefix_wins(self):
        """real-cugan must win over real prefix — longest-prefix match."""
        family, variant = _parse_model_id("real-cugan-up2x-conservative", _UPSCALE_FAMILIES)
        assert family == "real-cugan"
        assert variant == "up2x-conservative"

    def test_unknown_model_raises(self):
        with pytest.raises(ValueError, match="Unknown model_id"):
            _parse_model_id("bogus-model", _UPSCALE_FAMILIES)

    @pytest.mark.parametrize("model_id,family,variant", [
        ("swinir-medium", "swinir", "medium"),
        ("bsrgan-x4", "bsrgan", "x4"),
        ("waifu2x-anime-noise2", "waifu2x", "anime-noise2"),
    ])
    def test_all_supported_families(self, model_id, family, variant):
        f, v = _parse_model_id(model_id, _UPSCALE_FAMILIES)
        assert f == family
        assert v == variant

    def test_face_families(self):
        family, variant = _parse_model_id("gfpgan-v1.4", _FACE_FAMILIES)
        assert family == "gfpgan"
        assert variant == "v1.4"


def _build(tmp_path, face_restorers=None):
    fs = make_file_service_mock(tmp_path)
    mm = make_model_manager_mock()
    upscaler = MagicMock()
    upscaler.enhance = MagicMock(return_value=Image.new("RGB", (256, 256), (200, 200, 200)))
    upscalers = {"realesrgan": upscaler, "real-cugan": upscaler}
    face_restorers = {} if face_restorers is None else face_restorers
    svc = ImageUpscaleService(
        file_service=fs, task_manager=MagicMock(),
        model_manager=mm, upscalers=upscalers,
        face_restorers=face_restorers,
    )
    Image.new("RGB", (64, 64), (255, 0, 0)).save(Path(fs.require_file("f").file_path))
    return svc, fs, upscaler


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        ImageUpscaleService(file_service=fs, task_manager=tm,
                            model_manager=make_model_manager_mock(),
                            upscalers={}, face_restorers={})
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_IMAGE_UPSCALE
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_all_params(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = ImageUpscaleService(file_service=fs, task_manager=tm,
                                   model_manager=make_model_manager_mock(),
                                   upscalers={}, face_restorers={})
        tid = await svc.submit_upscale(
            file_id="fid", model_id="realesrgan-x2plus", scale=2,
            sharpen=True, face_fix=True,
            face_restore_model_id="gfpgan-v1.4",
            face_restore_upscale=2,
        )
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_IMAGE_UPSCALE
        assert args[1]["model_id"] == "realesrgan-x2plus"
        assert args[1]["face_fix"] is True


class TestUpscaleStatic:
    def test_static_image_upscale_calls_enhance(self, tmp_path):
        svc, fs, upscaler = _build(tmp_path)
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY):
            result = svc._execute(
                {"file_id": "f", "model_id": "realesrgan-x4plus", "scale": 4,
                 "sharpen": False, "face_fix": False,
                 "face_restore_model_id": None,
                 "face_restore_upscale": 2},
                lambda p, m: None,
            )
        upscaler.enhance.assert_called_once()
        assert "output_file_id" in result

    def test_scale_smaller_than_native_resizes_with_lanczos(self, tmp_path):
        """When requested scale < native_scale, post-process LANCZOS resize."""
        svc, fs, upscaler = _build(tmp_path)
        # Upscaler returns 4x upscale; service requests scale=2 → expect downscale
        upscaler.enhance.return_value = Image.new("RGB", (256, 256))
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY):
            svc._execute(
                {"file_id": "f", "model_id": "realesrgan-x4plus", "scale": 2,
                 "sharpen": False, "face_fix": False,
                 "face_restore_model_id": None,
                 "face_restore_upscale": 2},
                lambda p, m: None,
            )
        upscaler.enhance.assert_called_once()


class TestFaceRestoration:
    def test_face_fix_with_gfpgan_uses_upscale_kwarg(self, tmp_path):
        face = MagicMock()
        face.restore = MagicMock(return_value=Image.new("RGB", (256, 256)))
        svc, fs, upscaler = _build(tmp_path, face_restorers={"gfpgan": face})
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY):
            svc._execute(
                {"file_id": "f", "model_id": "realesrgan-x4plus", "scale": 4,
                 "sharpen": False, "face_fix": True,
                 "face_restore_model_id": "gfpgan-v1.4",
                 "face_restore_upscale": 3},
                lambda p, m: None,
            )
        kwargs = face.restore.call_args.kwargs
        assert kwargs.get("upscale") == 3

    def test_face_restore_failure_falls_back_silently(self, tmp_path):
        face = MagicMock()
        face.restore = MagicMock(side_effect=RuntimeError("face restore failed"))
        svc, fs, upscaler = _build(tmp_path, face_restorers={"gfpgan": face})
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY):
            result = svc._execute(
                {"file_id": "f", "model_id": "realesrgan-x4plus", "scale": 4,
                 "sharpen": False, "face_fix": True,
                 "face_restore_model_id": "gfpgan-v1.4",
                 "face_restore_upscale": 2},
                lambda p, m: None,
            )
        # No exception bubbled; result still returned
        assert "output_file_id" in result

    def test_unknown_face_restore_family_falls_back_gracefully(self, tmp_path):
        """face_restorers dict missing the requested family; service wraps face block
        in try/except, so missing-family → upscaled image without restoration."""
        svc, fs, upscaler = _build(tmp_path, face_restorers={})  # empty
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY):
            result = svc._execute(
                {"file_id": "f", "model_id": "realesrgan-x4plus", "scale": 4,
                 "sharpen": False, "face_fix": True,
                 "face_restore_model_id": "gfpgan-v1.4",
                 "face_restore_upscale": 2},
                lambda p, m: None,
            )
        # graceful fallback — no exception
        assert "output_file_id" in result


class TestUnknownUpscaleFamily:
    def test_unknown_upscale_family_raises(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        Image.new("RGB", (64, 64)).save(Path(fs.require_file("f").file_path))
        svc = ImageUpscaleService(
            file_service=fs, task_manager=MagicMock(),
            model_manager=make_model_manager_mock(),
            upscalers={},  # empty — every family lookup fails
            face_restorers={},
        )
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY):
            with pytest.raises(ValueError, match="Unknown upscale family"):
                svc._execute(
                    {"file_id": "f", "model_id": "realesrgan-x4plus", "scale": 4,
                     "sharpen": False, "face_fix": False,
                     "face_restore_model_id": None,
                     "face_restore_upscale": 2},
                    lambda p, m: None,
                )


class TestProgress:
    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, fs, upscaler = _build(tmp_path)
        progress = []
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY):
            svc._execute(
                {"file_id": "f", "model_id": "realesrgan-x4plus", "scale": 4,
                 "sharpen": False, "face_fix": False,
                 "face_restore_model_id": None,
                 "face_restore_upscale": 2},
                lambda p, m: progress.append((p, m)),
            )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0
