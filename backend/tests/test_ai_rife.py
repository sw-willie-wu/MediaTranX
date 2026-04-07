"""Integration tests for RIFE frame interpolation.

Requires: GPU + RIFE model.
Run: pytest -m ai
"""
import pytest
import numpy as np

pytestmark = pytest.mark.ai


@pytest.fixture
def rife():
    from app.engine.ai.video.rife import get_rife
    return get_rife()


def _model_available(rife, variant="v4.26"):
    try:
        rife._load_model(variant)
        rife._unload()
        return True
    except (FileNotFoundError, Exception):
        return False


class TestRIFE:
    def test_get_rife_returns_instance(self, rife):
        assert rife is not None

    def test_interpolate_two_frames(self, rife):
        if not _model_available(rife):
            pytest.skip("RIFE model not downloaded")

        frame0 = np.zeros((64, 64, 3), dtype=np.uint8)
        frame1 = np.full((64, 64, 3), 255, dtype=np.uint8)

        mid_frames = rife.interpolate_np(frame0, frame1, num_mid=1)
        assert len(mid_frames) == 1
        assert mid_frames[0].shape == (64, 64, 3)
        # Mid-frame should be somewhere between black and white
        mean_val = mid_frames[0].mean()
        assert 50 < mean_val < 200

    def test_interpolate_multiple_mids(self, rife):
        if not _model_available(rife):
            pytest.skip("RIFE model not downloaded")

        frame0 = np.zeros((32, 32, 3), dtype=np.uint8)
        frame1 = np.full((32, 32, 3), 255, dtype=np.uint8)

        mid_frames = rife.interpolate_np(frame0, frame1, num_mid=3)
        assert len(mid_frames) == 3
