"""
RIFE (Real-Time Intermediate Flow Estimation) wrapper.
Loads RIFE model and interpolates between frame pairs.
"""
from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import Optional, Callable

import numpy as np
import torch
from PIL import Image

from app.init.configs import SETTINGS
from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_RIFE
from app.init.container import get_container

logger = logging.getLogger(__name__)


def _fmt_time(seconds: float) -> str:
    """Format seconds to MM:SS or HH:MM:SS."""
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


class RIFEWrapper:
    """RIFE frame interpolation engine."""

    def __init__(self):
        self._model = None
        self._device = None
        self._variant = None
        self._manager = get_container().model_manager()
        logger.info("RIFEWrapper initialized")

    def _get_model_path(self, variant: str) -> Path:
        family = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("rife", {})
        variant_spec = family.get("variants", {}).get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown RIFE variant: {variant}")
        model_path = SETTINGS.path.models / SLOT_RIFE / variant_spec["filename"]
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

    def _np_to_tensor(self, arr: np.ndarray) -> torch.Tensor:
        """Convert HWC uint8 numpy array to NCHW float tensor on device."""
        return torch.from_numpy(arr.astype(np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0).to(self._device)

    def _tensor_to_np(self, tensor: torch.Tensor) -> np.ndarray:
        """Convert NCHW float tensor to HWC uint8 numpy array."""
        return (tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)

    def interpolate_np(self, arr0: np.ndarray, arr1: np.ndarray, num_mid: int = 1) -> list[np.ndarray]:
        """Interpolate between two numpy frames (H,W,3 uint8). Returns list of mid frames."""
        assert self._model is not None, "Model not loaded"
        t0 = self._np_to_tensor(arr0)
        t1 = self._np_to_tensor(arr1)
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
                results.append(self._tensor_to_np(mid[:, :, :h, :w]))
            else:
                for i in range(1, num_mid + 1):
                    t = i / (num_mid + 1)
                    mid = self._model(t0, t1, timestep=t)
                    results.append(self._tensor_to_np(mid[:, :, :h, :w]))
        return results

    def interpolate(self, img0: Image.Image, img1: Image.Image, num_mid: int = 1) -> list[Image.Image]:
        """Interpolate between two PIL images. Returns list of mid frames."""
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
        self, frames_dir: Path, output_dir: Path, variant: str = "v4.26",
        multiplier: int = 2, fmt: str = "jpg",
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> tuple[int, float]:
        from concurrent.futures import ThreadPoolExecutor
        import shutil

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

        # Prefetch: use thread to preload next frame + async file saving
        write_pool = ThreadPoolExecutor(max_workers=4)
        write_futures = []

        def save_frame(img: Image.Image, path: Path):
            img.save(path)

        # Preload first frame
        current_img = Image.open(frame_files[0])

        for i in range(len(frame_files)):
            # Copy original frame to output (write file via thread)
            out_path = output_dir / f"{out_idx:06d}.{fmt}"
            write_futures.append(write_pool.submit(save_frame, current_img, out_path))
            out_idx += 1

            if i < total_pairs:
                # Preload next frame (start reading before GPU inference)
                next_img = Image.open(frame_files[i + 1])

                # GPU inference
                mid_frames = self.interpolate(current_img, next_img, num_mid=num_mid)

                # Async write interpolated frame
                for mid in mid_frames:
                    mid_path = output_dir / f"{out_idx:06d}.{fmt}"
                    write_futures.append(write_pool.submit(save_frame, mid, mid_path))
                    out_idx += 1

                current_img = next_img

                if on_progress:
                    pct = (i + 1) / total_pairs
                    on_progress(pct, f"task.progress.interpolating_pair|{i + 1}|{total_pairs}")

        # Wait for all writes to complete
        for f in write_futures:
            f.result()
        write_pool.shutdown(wait=False)

        self._unload()
        total_output = out_idx - 1
        logger.info(f"Interpolated {total_pairs} pairs → {total_output} frames ({multiplier}x)")
        return total_output, multiplier


    def interpolate_pipe(
        self,
        input_path: str | Path,
        output_path: str | Path,
        variant: str = "v4.26",
        multiplier: int = 2,
        width: int = 0,
        height: int = 0,
        source_fps: float = 30.0,
        duration: float = 0.0,
        target_fps: float | Fraction = 0,
        video_codec: str = "h264",
        on_progress: Optional[Callable[[float, str], None]] = None,
        output_fps: float | Fraction | None = None,
    ) -> tuple[int, float]:
        """
        Pipe-based interpolation: FFmpeg decode → RIFE → FFmpeg encode.
        No temp files on disk. If target_fps is set and differs from
        source_fps * multiplier, FFmpeg fps filter trims to exact target.
        """
        from app.utils.video_frames import FramePipe

        self._load_model(variant)
        num_mid = multiplier - 1
        if output_fps is None:
            output_fps = source_fps * multiplier

        pipe = FramePipe(
            input_path, output_path,
            output_fps=output_fps,
            input_width=width, input_height=height,
            output_width=width, output_height=height,
            video_codec=video_codec,
            target_fps=target_fps,
        )
        pipe.open()

        # Async encoder: use queue + thread to decouple GPU inference and FFmpeg encoding
        from queue import Queue
        from threading import Thread

        write_queue: Queue[np.ndarray | None] = Queue(maxsize=32)

        def _encoder_thread():
            while True:
                item = write_queue.get()
                if item is None:
                    break
                pipe.write_frame(item)

        writer = Thread(target=_encoder_thread, daemon=True)
        writer.start()

        try:
            prev_frame = None
            frame_idx = 0
            total_written = 0

            for frame in pipe.read_frames():
                if prev_frame is not None:
                    write_queue.put(prev_frame)
                    total_written += 1

                    mid_frames = self.interpolate_np(prev_frame, frame, num_mid=num_mid)
                    for mid in mid_frames:
                        write_queue.put(mid)
                        total_written += 1
                    del mid_frames

                    if on_progress:
                        elapsed = frame_idx / source_fps
                        if duration > 0:
                            pct = min(elapsed / duration, 0.99)
                            on_progress(pct, f"task.progress.interpolating_time|{_fmt_time(elapsed)}|{_fmt_time(duration)}")
                        else:
                            on_progress(0.5, f"task.progress.interpolating_elapsed|{_fmt_time(elapsed)}")

                prev_frame = frame
                frame_idx += 1

            # Write last frame
            if prev_frame is not None:
                write_queue.put(prev_frame)
                total_written += 1

            # Signal encoder thread to stop
            write_queue.put(None)
            writer.join()

        finally:
            pipe.close()
            self._unload()

        logger.info(f"Pipe interpolated {frame_idx} frames → {total_written} frames ({multiplier}x)")
        return total_written, multiplier


_rife: Optional[RIFEWrapper] = None

def get_rife() -> RIFEWrapper:
    global _rife
    if _rife is None:
        _rife = RIFEWrapper()
    return _rife
