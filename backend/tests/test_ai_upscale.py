"""Integration tests for Real-ESRGAN image upscaling.

Requires: GPU + Real-ESRGAN model.
Run: pytest -m ai
"""
import pytest

pytestmark = pytest.mark.ai


@pytest.fixture
def realesrgan():
    from app.engine.ai.image import get_upscaler
    return get_upscaler("realesrgan")


class TestRealESRGAN:
    def test_get_upscaler_returns_instance(self, realesrgan):
        assert realesrgan is not None

    def test_enhance_small_image(self, realesrgan):
        """Upscale a tiny test image."""
        from PIL import Image
        from app.init.configs import SETTINGS

        # Check if model is downloaded
        model_dir = SETTINGS.path.models / "image" / "realesrgan"
        if not model_dir.exists() or not any(model_dir.glob("*.pth")):
            pytest.skip("Real-ESRGAN model not downloaded")

        img = Image.new("RGB", (64, 64), color=(128, 128, 128))
        progress_calls = []
        result = realesrgan.enhance(
            image=img,
            model_id="x4plus",
            scale=4,
            on_progress=lambda p, m: progress_calls.append((p, m)),
        )
        assert isinstance(result, Image.Image)
        assert result.size[0] == 256  # 64 * 4
        assert result.size[1] == 256
        assert len(progress_calls) > 0
