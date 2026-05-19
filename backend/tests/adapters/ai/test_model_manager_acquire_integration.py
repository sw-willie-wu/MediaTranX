"""Integration test: ModelManager + container wiring + wrapper.acquire round-trip.

Regression guard for bug-#3 (slot mismatch). If any wrapper's slot key drifts
from the container's register_dispatcher / register_runtime_provider key,
mm.acquire() raises KeyError. This test catches that immediately.

We use a real ModelManager and real container.init_container() but mock
PthWrapper._load_impl / PackageWrapper._create_model + subclass-level
_resolve_model_path overrides so no real model loads.
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def container():
    """Fresh AppContainer with full init_container() wiring."""
    from app.init.container import init_container
    return init_container()


@pytest.fixture(autouse=True)
def _stub_real_loads():
    """Stub out _load_impl / _create_model / _resolve_model_path across all
    wrappers so we never actually load PyTorch / faster-whisper / etc.

    NOTE: MobileSAMWrapper and WhisperWrapper override _resolve_model_path
    on the subclass. Class-level patches on PackageWrapper.* don't catch
    subclass overrides via MRO — must patch each subclass directly.
    """
    from app.adapters.ai.wrapper.base import PthWrapper, PackageWrapper
    from app.adapters.ai.wrapper.mobilesam import MobileSAMWrapper
    from app.adapters.ai.wrapper.whisper import WhisperWrapper

    fake_resolve = lambda *a, **k: ("/fake/path", {"_key": "fake"})

    with patch.object(PthWrapper, "_load_impl", return_value=MagicMock()), \
         patch.object(PthWrapper, "_unload_impl"), \
         patch.object(PackageWrapper, "_load_impl", return_value=MagicMock()), \
         patch.object(PackageWrapper, "_unload_impl"), \
         patch.object(PthWrapper, "_resolve_model_path", side_effect=fake_resolve), \
         patch.object(MobileSAMWrapper, "_resolve_model_path", side_effect=fake_resolve), \
         patch.object(WhisperWrapper, "_resolve_model_path", side_effect=fake_resolve):
        yield


@pytest.mark.parametrize("family", [
    "realesrgan", "bsrgan", "swinir", "real-cugan", "waifu2x",
])
def test_upscale_dispatch_acquires_correct_wrapper(container, family):
    """mm.acquire('upscale', family) should return the family-specific wrapper."""
    mm = container.model_manager()
    with mm.acquire(slot="upscale", model_id=family, variant="default") as runtime:
        # runtime is the family wrapper; class-name contains family token
        cls_name = runtime.__class__.__name__.lower()
        token = family.replace("-", "").replace("_", "")
        assert token in cls_name or token[:6] in cls_name, (
            f"upscale dispatcher returned {runtime.__class__.__name__} for family {family!r}"
        )


@pytest.mark.parametrize("family", ["gfpgan"])
def test_face_restore_dispatch_acquires_correct_wrapper(container, family):
    mm = container.model_manager()
    with mm.acquire(slot="face_restore", model_id=family, variant="default") as runtime:
        assert family in runtime.__class__.__name__.lower()


def test_mobilesam_provider_acquires(container):
    mm = container.model_manager()
    with mm.acquire(slot="mobilesam", model_id="mobilesam", variant=None) as runtime:
        assert "MobileSAM" in runtime.__class__.__name__


def test_wrapper_self_acquire_works_via_dispatcher(container):
    """The bug-#3 production failure path: wrapper.enhance() calls self.acquire(),
    which calls mm.acquire(slot=self.slot, ...). With slot='upscale', the
    dispatcher routes back to the same wrapper. Verify the round-trip."""
    realesrgan = container.upscalers()["realesrgan"]
    # Manually attach _model_manager since wrapper hasn't been acquired yet
    # (dispatcher path only attaches on first mm.acquire call).
    realesrgan._model_manager = container.model_manager()

    with realesrgan.acquire(model_id="realesrgan", variant="x4plus") as runtime:
        assert runtime is realesrgan
