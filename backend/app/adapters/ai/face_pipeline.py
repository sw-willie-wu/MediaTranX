"""Face-restoration pipeline: detect → align → restore → paste-back.

Wraps facexlib.FaceRestoreHelper to give the GFPGAN wrapper a
model-agnostic per-face inference orchestrator. The actual restoration
model is supplied via a callable per restore() invocation.

facexlib downloads its detector / parser weights on first use to
~/.cache/torch/hub/checkpoints/ (~150 MB). This is intentional.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)

# Module-level reference kept for test patching (patch("…face_pipeline.FaceRestoreHelper")).
# Populated lazily on first _ensure_helper() call — cold start unaffected.
FaceRestoreHelper: Any = None


class FacePipeline:
    """Detect → align → restore per face → paste-back orchestrator.

    Stateful: lazily builds a facexlib FaceRestoreHelper on first restore()
    call and caches it for the wrapper's lifetime. clean_all() is called
    between invocations so per-image state (landmarks, cropped_faces) resets.
    """

    def __init__(self, device: str = "cuda"):
        self._device = device
        self._helper: Optional[Any] = None  # FaceRestoreHelper, lazy
        self._cached_upscale: Optional[int] = None

    def _ensure_helper(self, upscale_factor: int) -> None:
        global FaceRestoreHelper
        # Always record the upscale factor — even when helper is already present
        # (e.g. injected by tests) so the upscale-change check in restore() is
        # correctly skipped on subsequent calls.
        self._cached_upscale = upscale_factor
        if self._helper is not None:
            return
        # Lazy import — keeps cold start unaffected when face restoration isn't used.
        if FaceRestoreHelper is None:
            from facexlib.utils.face_restoration_helper import FaceRestoreHelper as _FRH
            FaceRestoreHelper = _FRH  # noqa: PLW0603 — intentional module-level caching

        self._helper = FaceRestoreHelper(
            upscale_factor=upscale_factor,
            face_size=512,
            crop_ratio=(1, 1),
            det_model="retinaface_resnet50",
            save_ext="png",
            use_parse=False,
            device=self._device,
        )
        logger.info(f"FacePipeline FaceRestoreHelper built on {self._device} (upscale={upscale_factor})")

    def restore(
        self,
        image: Image.Image,
        restore_fn: Callable[[torch.Tensor], torch.Tensor],
        *,
        face_upscale: int = 2,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """Run detect → restore (per face) → paste-back.

        Args:
            image: Full-resolution input PIL image.
            restore_fn: Callable taking an NCHW float [0,1] tensor of shape
                (1, 3, 512, 512) on `self._device` and returning a tensor of
                identical shape (also on `self._device`).
            face_upscale: Target paste-back upscale factor (passed to helper).
            on_progress: (start ≈ 0.05, per face ≈ 0.05..0.95, final ≈ 0.95..1.0).

        Returns:
            Composited image with restored faces. If no faces detected,
            returns the input image unchanged.
        """
        self._ensure_helper(upscale_factor=face_upscale)
        helper = self._helper
        assert helper is not None  # set by _ensure_helper

        helper.clean_all()
        # NOTE: upscale_factor is baked at helper construction. If face_upscale
        # differs across calls within the same wrapper lifetime, rebuild the
        # helper so the inverse-affine math stays correct.
        if self._cached_upscale != face_upscale:
            self._helper = None
            self._cached_upscale = face_upscale
            self._ensure_helper(upscale_factor=face_upscale)
            helper = self._helper

        # facexlib accepts ndarray BGR; PIL is RGB so convert
        img_rgb = np.array(image.convert("RGB"))
        img_bgr = img_rgb[:, :, ::-1]
        helper.read_image(img_bgr)

        if on_progress:
            on_progress(0.05, "task.progress.face_detect")

        num_faces = helper.get_face_landmarks_5(
            only_center_face=False, resize=640, eye_dist_threshold=5,
        )
        if num_faces == 0:
            logger.info("FacePipeline: no faces detected; returning original image")
            return image

        helper.align_warp_face()

        # Restore each cropped face
        for i, cropped in enumerate(helper.cropped_faces):
            if on_progress:
                on_progress(
                    0.05 + 0.85 * (i / max(num_faces, 1)),
                    f"task.progress.face_restore|{i + 1}|{num_faces}",
                )
            face_tensor = self._face_to_tensor(cropped)
            restored = restore_fn(face_tensor)
            restored_face = self._tensor_to_face(restored)
            helper.add_restored_face(restored_face)

        helper.get_inverse_affine(None)

        if on_progress:
            on_progress(0.95, "task.progress.face_paste_back")

        # paste returns BGR ndarray; convert back to RGB PIL
        composite_bgr = helper.paste_faces_to_input_image(upsample_img=None)
        composite_rgb = composite_bgr[:, :, ::-1]
        result = Image.fromarray(composite_rgb.astype(np.uint8))

        if on_progress:
            on_progress(1.0, "task.progress.face_restore_complete")

        return result

    def _face_to_tensor(self, cropped: np.ndarray) -> torch.Tensor:
        """Convert facexlib cropped face (BGR uint8 HWC) → NCHW float [0,1] RGB tensor on device."""
        # cropped is BGR per facexlib convention; convert to RGB
        rgb = cropped[:, :, ::-1].copy()
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        return tensor.unsqueeze(0).to(self._device)

    def _tensor_to_face(self, tensor: torch.Tensor) -> np.ndarray:
        """Convert NCHW float [0,1] RGB tensor → BGR uint8 HWC ndarray (facexlib format)."""
        rgb = (tensor.squeeze(0).clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255.0).astype(np.uint8)
        return rgb[:, :, ::-1].copy()  # back to BGR
