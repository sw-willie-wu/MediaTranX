"""Integration tests for RIFE frame interpolation.

Requires: GPU + RIFE model.
Run: pytest -m ai
"""
import pytest
import numpy as np

pytestmark = pytest.mark.ai


@pytest.fixture
def rife():
    """RIFE wrapper wired through DI container so _model_manager is set."""
    from app.init.container import init_container
    c = init_container()
    w = c.rife_wrapper()
    w._model_manager = c.model_manager()
    return w


def _rife_model_downloaded(variant="v4.26") -> bool:
    """Check the flownet-<variant>.pkl file exists on disk (per registry)."""
    from app.init.configs import SETTINGS
    return (SETTINGS.path.models / "rife" / f"flownet-{variant}.pkl").exists()


class TestRIFE:
    def test_rife_wrapper_instantiable(self, rife):
        assert rife is not None

    def test_interpolate_two_frames(self, rife):
        if not _rife_model_downloaded():
            pytest.skip("RIFE model not downloaded")

        # interpolate_np asserts self.is_loaded() — wrap in acquire context.
        with rife.acquire(model_id="rife", variant="v4.26"):
            frame0 = np.zeros((64, 64, 3), dtype=np.uint8)
            frame1 = np.full((64, 64, 3), 255, dtype=np.uint8)

            mid_frames = rife.interpolate_np(frame0, frame1, num_mid=1)
            assert len(mid_frames) == 1
            assert mid_frames[0].shape == (64, 64, 3)
            # Mid-frame should be somewhere between black and white
            mean_val = mid_frames[0].mean()
            assert 50 < mean_val < 200

    def test_interpolate_multiple_mids(self, rife):
        if not _rife_model_downloaded():
            pytest.skip("RIFE model not downloaded")

        with rife.acquire(model_id="rife", variant="v4.26"):
            frame0 = np.zeros((32, 32, 3), dtype=np.uint8)
            frame1 = np.full((32, 32, 3), 255, dtype=np.uint8)

            mid_frames = rife.interpolate_np(frame0, frame1, num_mid=3)
            assert len(mid_frames) == 3
