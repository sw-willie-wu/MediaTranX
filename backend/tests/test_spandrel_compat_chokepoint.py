"""WS2 Task 2: the torchvision functional_tensor compat shim must be applied
at the spandrel model-load chokepoint (before `import spandrel`), since basicsr
— the sole consumer of the removed module — could be pulled by a spandrel load.
"""
import sys
import types
from unittest import mock


def test_load_with_spandrel_applies_compat_before_importing_spandrel():
    from app.adapters.ai.wrapper.realesrgan import RealESRGANWrapper
    w = RealESRGANWrapper()  # PthWrapper subclass, use_spandrel=True; no ctor args

    calls = []
    fake_spandrel = types.ModuleType("spandrel")

    class _Loader:
        def load_from_file(self, path):
            calls.append("spandrel.load")
            m = mock.MagicMock()
            m.to.return_value = m
            return m

    fake_spandrel.ModelLoader = lambda: _Loader()

    with mock.patch("app.init.compat.ensure_torchvision_functional_tensor_compat") as ensure, \
         mock.patch.dict(sys.modules, {"spandrel": fake_spandrel}):
        ensure.side_effect = lambda: calls.append("ensure")
        w._load_with_spandrel(__file__, "cpu", {})

    # The shim must run, and BEFORE spandrel is used.
    assert "ensure" in calls, "compat shim not applied at the chokepoint"
    assert calls.index("ensure") < calls.index("spandrel.load"), "shim applied after spandrel use"
