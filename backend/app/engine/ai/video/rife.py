"""
RIFE (Real-Time Intermediate Flow Estimation) wrapper.
Loads RIFE model and interpolates between frame pairs.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Callable

import numpy as np
import torch
from PIL import Image

from app.engine.paths import get_models_dir
from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_RIFE
from app.engine.ai.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class RIFEWrapper:
    """RIFE frame interpolation engine."""

    def __init__(self):
        self._model = None
        self._device = None
        self._variant = None
        self._manager = get_model_manager()
        logger.info("RIFEWrapper initialized")

    def _get_model_path(self, variant: str) -> Path:
        family = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("rife", {})
        variant_spec = family.get("variants", {}).get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown RIFE variant: {variant}")
        model_path = get_models_dir() / SLOT_RIFE / variant_spec["filename"]
        if not model_path.exists():
            raise FileNotFoundError(
                f"RIFE model not found: {model_path}. "
                "Please download via Settings → Model Management."
            )
        return model_path

    def _load_model(self, variant: str):
        if self._model is not None and self._variant == variant:
            return
        model_path = self._get_model_path(variant)
        if torch.cuda.is_available():
            self._device = torch.device("cuda")
        else:
            self._device = torch.device("cpu")
        state_dict = torch.load(model_path, map_location=self._device, weights_only=True)
        from app.engine.ai.video._rife_arch import IFNet
        model = IFNet()
        model.load_state_dict(state_dict, strict=False)
        model.eval()
        model.to(self._device)
        self._model = model
        self._variant = variant
        logger.info(f"RIFE {variant} loaded on {self._device}")

    def _unload(self):
        if self._model is not None:
            del self._model
            self._model = None
            self._variant = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def interpolate(self, img0: Image.Image, img1: Image.Image, num_mid: int = 1) -> list[Image.Image]:
        assert self._model is not None, "Model not loaded"
        def to_tensor(img: Image.Image) -> torch.Tensor:
            arr = np.array(img.convert("RGB")).astype(np.float32) / 255.0
            return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(self._device)
        t0 = to_tensor(img0)
        t1 = to_tensor(img1)
        h, w = t0.shape[2], t0.shape[3]
        ph = ((h - 1) // 32 + 1) * 32
        pw = ((w - 1) // 32 + 1) * 32
        pad = torch.nn.functional.pad
        t0 = pad(t0, (0, pw - w, 0, ph - h))
        t1 = pad(t1, (0, pw - w, 0, ph - h))
        results = []
        with torch.no_grad():
            if num_mid == 1:
                mid = self._model(t0, t1, timestep=0.5)
                mid = mid[:, :, :h, :w]
                results.append(self._tensor_to_image(mid))
            else:
                for i in range(1, num_mid + 1):
                    t = i / (num_mid + 1)
                    mid = self._model(t0, t1, timestep=t)
                    mid = mid[:, :, :h, :w]
                    results.append(self._tensor_to_image(mid))
        return results

    @staticmethod
    def _tensor_to_image(tensor: torch.Tensor) -> Image.Image:
        arr = (tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        return Image.fromarray(arr)

    def interpolate_sequence(
        self, frames_dir: Path, output_dir: Path, variant: str = "v4.22",
        multiplier: int = 2, fmt: str = "jpg",
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> tuple[int, float]:
        self._load_model(variant)
        output_dir.mkdir(parents=True, exist_ok=True)
        frame_files = sorted(frames_dir.glob(f"*.{fmt}"))
        if not frame_files:
            frame_files = sorted(frames_dir.glob("*.png"))
            fmt = "png"
        if not frame_files:
            raise RuntimeError(f"No frames found in {frames_dir}")
        total_pairs = len(frame_files) - 1
        num_mid = multiplier - 1
        out_idx = 1
        for i, frame_path in enumerate(frame_files):
            img = Image.open(frame_path)
            img.save(output_dir / f"{out_idx:06d}.{fmt}")
            out_idx += 1
            if i < total_pairs:
                next_img = Image.open(frame_files[i + 1])
                mid_frames = self.interpolate(img, next_img, num_mid=num_mid)
                for mid in mid_frames:
                    mid.save(output_dir / f"{out_idx:06d}.{fmt}")
                    out_idx += 1
                if on_progress:
                    pct = (i + 1) / total_pairs
                    on_progress(pct, f"補幀中 {pct:.0%} ({i + 1}/{total_pairs} 對)")
        self._unload()
        total_output = out_idx - 1
        logger.info(f"Interpolated {total_pairs} pairs → {total_output} frames ({multiplier}x)")
        return total_output, multiplier


_rife: Optional[RIFEWrapper] = None

def get_rife() -> RIFEWrapper:
    global _rife
    if _rife is None:
        _rife = RIFEWrapper()
    return _rife
