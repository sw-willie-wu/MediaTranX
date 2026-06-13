"""Real-binary smoke test for the ncnn-vulkan SR wrappers (T8 / NFR2).

Runs the ACTUAL realesrgan / waifu2x ncnn-vulkan CLIs on a tiny image through
the production model wrappers, asserting the real CLI contracts the mocked
unit tests cannot (realesrgan never prints `100.00%`; waifu2x only loads when
the `-m` dir basename is `models-cunet`) plus an NFR2 GPU-device-line check.

HERMETIC + env-gated: it points SETTINGS.path at a dedicated root given by
`MEDIATRANX_NCNN_SMOKE_ROOT`, laid out as

    <root>/bin/ncnn/<tool>/<tool>-ncnn-vulkan.exe  (+ vcomp140.dll)
    <root>/models/realesrgan/realesrgan-x4plus.{param,bin}
    <root>/models/waifu2x/models-cunet/scale2.0x_model.{param,bin}

Skips when the env var is unset or the layout is incomplete, so CI is a no-op.
It uses a dedicated root rather than the default `models/` slot so it stays
independent of any locally-downloaded models and of the other AI tests.
Marked `ai`: deselected by the default `-m "not ai"` run.
"""
from __future__ import annotations

import os
import pathlib
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from PIL import Image

from app.adapters.ai.model_manager import ModelManager
from app.adapters.ai.wrapper.realesrgan import RealESRGANWrapper
from app.adapters.ai.wrapper.waifu2x import Waifu2xWrapper

pytestmark = pytest.mark.ai

SMOKE_ROOT_ENV = "MEDIATRANX_NCNN_SMOKE_ROOT"
_WRAPPER = {"realesrgan": RealESRGANWrapper, "waifu2x": Waifu2xWrapper}


@pytest.fixture
def smoke_paths(monkeypatch):
    """Point SETTINGS.path.ncnn/.models at the dedicated smoke root (or skip)."""
    root = os.environ.get(SMOKE_ROOT_ENV)
    if not root:
        pytest.skip(f"set {SMOKE_ROOT_ENV} to a prepared smoke root to run "
                    f"(bin/ncnn/<tool>/<exe> + models/<slot>/...)")
    root = pathlib.Path(root)
    from app.init.configs import SETTINGS
    monkeypatch.setattr(SETTINGS.path, "root", root)         # drives SETTINGS.path.ncnn
    monkeypatch.setattr(SETTINGS.path, "models", root / "models")
    return root


def _model_dict(family: str, variant: str):
    """Build the wrapper's `_model` from the (now smoke-rooted) install, or None."""
    mm = ModelManager()
    cfg = mm.get_model_config(family, variant)
    param = mm.get_model_path(family, variant)
    if not cfg or param is None:
        return None
    try:
        _WRAPPER[family]()._ncnn.exe_path()    # guard: the ncnn exe is installed
    except FileNotFoundError:
        return None
    return {"model_dir": param.parent, "config": {**cfg, "variant": variant}}


def _fake_acquire(w, model):
    @contextmanager
    def _acq(model_id=None, variant=None, on_progress=None):
        w._model = model
        yield w
    return _acq


@pytest.mark.parametrize("family,variant,scale", [
    ("realesrgan", "x4plus", 4),
    ("waifu2x", "cunet-art-2x", 2),
])
def test_real_cli_upscales_and_reports_gpu(smoke_paths, family, variant, scale):
    model = _model_dict(family, variant)
    if model is None:
        pytest.skip(f"{family}/{variant}: exe or weights missing under {smoke_paths}")

    # waifu2x only loads when -m's basename is models-cunet (the bug T8 caught):
    # assert the resolved model_dir really is that nested dir.
    if family == "waifu2x":
        assert model["model_dir"].name == "models-cunet", model["model_dir"]

    w = _WRAPPER[family]()
    progress: list[float] = []
    src = Image.new("RGB", (48, 48), (123, 222, 64))
    with patch.object(w, "acquire", _fake_acquire(w, model)):
        out = w.enhance(src, model_id=variant,
                        on_progress=lambda p, m: progress.append(p))

    # functional: the CLI actually ran and produced a native-scale upscale.
    assert out.size == (48 * scale, 48 * scale)
    # NFR2: a Vulkan device line was captured → the GPU path ran, not a silent
    # CPU miss (both CLIs print "[<idx> <device name>] ..." on init).
    assert any(line.lstrip().startswith("[") and "]" in line
               for line in w.last_run_lines), \
        f"no Vulkan device line captured: {w.last_run_lines[:4]}"
    # progress stayed inside the inference band and moved.
    assert progress and all(p >= 1.0 for p in progress)
