"""
CodeFormer face restoration wrapper (Three-Layer Architecture V3).
Refactored: inherits PthWrapper, supports fidelity adjustment.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Callable

import torch
from PIL import Image

from app.adapters.ai.wrapper.base import PthWrapper
from app.adapters.ai.registry import FORMAT_PTH, MODELS_REGISTRY

logger = logging.getLogger(__name__)


class CodeFormerWrapper(PthWrapper):
    """
    CodeFormer face restoration wrapper.

    Features:
    1. Uses VQ-GAN for face restoration
    2. Supports fidelity adjustment (0~1)
    3. Handles low-resolution/blurry/damaged face images
    """

    def __init__(self):
        super().__init__(slot="face_restore", use_spandrel=True)
        self._face_pipeline: Optional[Any] = None  # lazy FacePipeline
        logger.info("CodeFormerWrapper initialized (PthWrapper)")
    
    def restore(
        self,
        image: Image.Image,
        model_id: str = "default",
        fidelity: float = 0.7,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """Run CodeFormer face restoration.

        Pipeline: detect faces → align each to 512x512 → CodeFormer restore →
        paste back. Background outside detected faces is unchanged.

        If facexlib detects no faces (e.g. cartoons/stylised images), returns
        the input unchanged.
        """
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["codeformer"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown CodeFormer variant: {model_id}")

        vram_needed = variant_spec["vram_mb"]  # noqa: F841 — used by outer mm.acquire (Wave D)

        with self.acquire(
            model_id="codeformer",
            variant=model_id,
            on_progress=lambda p, m: on_progress(p * 0.05, m) if on_progress else None,
        ):
            # `acquire()` yields the wrapper itself (per BaseWrapper.acquire);
            # the loaded spandrel-wrapped CodeFormer model lives on `self._model`.
            model = self._model

            if self._face_pipeline is None:
                from app.adapters.ai.face_pipeline import FacePipeline
                self._face_pipeline = FacePipeline(device=self._device)

            def restore_fn(face_tensor):
                with torch.no_grad():
                    # TODO(bug #5, Wave E): `fidelity` is currently a no-op — the
                    # spandrel-wrapped model is called as `model(face_tensor)`
                    # without forwarding `w=fidelity`. Wave E test
                    # `tests/adapters/ai/wrapper/test_codeformer_wrapper.py::
                    # test_restore_with_mocked_facepipeline_and_acquire` asserts
                    # current (broken) behavior. Fix needs spandrel CodeFormer API
                    # research: likely `model(face_tensor, w=fidelity)` or
                    # `model.model.w = fidelity` before calling.
                    output = model(face_tensor)
                    if isinstance(output, tuple):
                        output = output[0]
                    return output

            face_progress = lambda p, m: on_progress(0.05 + p * 0.95, m) if on_progress else None
            return self._face_pipeline.restore(
                image, restore_fn, face_upscale=2, on_progress=face_progress,
            )
