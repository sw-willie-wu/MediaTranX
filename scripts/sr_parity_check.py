"""T9 parity measurement: ncnn-vulkan SR output vs the current torch/spandrel SR
output, on a fixed fixture set. Loads the torch wrappers standalone (spandrel,
no DI container) for the reference, runs the production NcnnUpscaleWrapper for
the candidate, and reports SSIM/PSNR via tests/parity/harness. Saves side-by-side
A/B PNGs under <out>/ab/ for visual inspection.

Run from backend/ with the smoke root populated (exes + ncnn weights) and a dir
of natural-image fixtures (the NFR1 PSNR>=40 bar assumes real content, not noise):
  MEDIATRANX_NCNN_SMOKE_ROOT=<root> SR_PARITY_FIXTURES=<photos> \
    uv run python ../scripts/sr_parity_check.py

NOTE: the torch reference path needs the spandrel-based RealESRGAN/Waifu2x
wrappers, which T11 replaced with the ncnn subclasses — so re-running requires a
pre-T11 checkout (or installing torch + spandrel and loading the .pth directly).
This file is retained as the recorded T9 result/methodology, below.

RESULT (2026-06-13, RTX 3080, input.jpg/input2.jpg canonical realesrgan photos):
  waifu2x  cunet-2x : SSIM 0.9999, PSNR 46-51 dB  → PASSES strict NFR1 (same
                      cunet/art/scale2x weights torch- and ncnn-side).
  realesrgan x4plus : SSIM 0.997-0.999, PSNR ~37-39 dB → SSIM bar met, PSNR a
                      hair under 40 from the ncnn-fp16 vs torch-fp32 gap. A/B is
                      visually indistinguishable (user-confirmed 2026-06-13).
DECISION (Willie, 2026-06-13): ACCEPT both → switch to ncnn (T10). realesrgan
gets a recorded spec NFR1 exception (PSNR ~38 dB fp16, perceptually identical;
covers the same-engine variants x4plus-anime / animevideov3-x2/x3/x4). Synthetic
high-frequency / random-noise inputs diverge more (expected) and are not the bar.
"""
from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.adapters.ai.wrapper.realesrgan import RealESRGANWrapper
from app.adapters.ai.wrapper.waifu2x import Waifu2xWrapper
from app.adapters.ai.wrapper.realesrgan import RealESRGANWrapper as _RealesrganNcnn
from app.adapters.ai.wrapper.waifu2x import Waifu2xWrapper as _Waifu2xNcnn
from app.adapters.ai.model_manager import ModelManager
from tests.parity.harness import ssim, psnr

OUT = Path(os.environ.get("SR_PARITY_OUT", "sr_parity_out"))
CACHE = OUT / "torch_weights"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# (family, variant, scale, torch .pth url, archive member or None, torch wrapper cls)
CASES = [
    ("realesrgan", "x4plus", 4,
     "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
     None, RealESRGANWrapper),
    ("waifu2x", "cunet-art-2x", 2,
     "https://github.com/nagadomi/nunif/releases/download/0.0.0/waifu2x_pretrained_models_20250502.zip",
     "pretrained_models/cunet/art/scale2x.pth", Waifu2xWrapper),
]


def _fixtures() -> dict[str, Image.Image]:
    """Natural-image fixtures from SR_PARITY_FIXTURES (the realistic content the
    NFR1 PSNR>=40 bar assumes) plus one synthetic high-frequency pattern as a
    deliberate worst case. Real images are centre-cropped to <=160px for speed."""
    out = {}
    fx_dir = os.environ.get("SR_PARITY_FIXTURES")
    if fx_dir:
        imgs = [p for p in sorted(Path(fx_dir).glob("*"))
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")]
        for p in imgs[:3]:
            if True:
                im = Image.open(p).convert("RGB")
                # centre-crop a 160px patch (keeps native detail, bounds SR cost)
                s = min(im.width, im.height, 160)
                l, t = (im.width - s) // 2, (im.height - s) // 2
                out[p.stem[:10]] = im.crop((l, t, l + s, t + s))
    yy, xx = np.mgrid[0:96, 0:96]            # synthetic worst case (always included)
    rings = (np.sin(np.hypot(xx - 48, yy - 48) / 2.0) * 127 + 128)
    grate = (np.sin((xx + yy) / 1.5) * 127 + 128)
    ramp = (xx / 96 * 255)
    out["synthetic"] = Image.fromarray(np.stack([rings, grate, ramp], -1).clip(0, 255).astype(np.uint8))
    return out


def _torch_pth(url: str, member: str | None, dst: Path) -> Path:
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading torch weights: {url}")
    blob = urllib.request.urlopen(url).read()
    if member:
        blob = zipfile.ZipFile(io.BytesIO(blob)).read(member)
    dst.write_bytes(blob)
    return dst


def _torch_ref(cls, pth: Path, img: Image.Image, variant: str, scale: int) -> Image.Image:
    w = cls()

    @contextmanager
    def _acq(model_id=None, variant=None, on_progress=None):
        w._device = DEVICE
        w._model = w._load_with_spandrel(pth, DEVICE, {})
        yield w

    with patch.object(w, "acquire", _acq):
        return w.enhance(img, model_id=variant, scale=scale)


_NCNN_WRAPPER = {"realesrgan": _RealesrganNcnn, "waifu2x": _Waifu2xNcnn}


def _ncnn_out(family: str, variant: str) -> "callable":
    mm = ModelManager()
    cfg = mm.get_model_config(family, variant)
    param = mm.get_model_path(family, variant)
    if not cfg or param is None:
        raise SystemExit(f"ncnn {family}/{variant} not installed under the smoke root")
    w = _NCNN_WRAPPER[family]()
    model = {"exe": str(w._exe_path()), "model_dir": param.parent,
             "config": {**cfg, "variant": variant}}

    @contextmanager
    def _acq(model_id=None, variant=None, on_progress=None):
        w._model = model
        yield w

    def run(img: Image.Image) -> Image.Image:
        with patch.object(w, "acquire", _acq):
            return w.enhance(img, model_id=variant)
    return run


def main() -> int:
    if not os.environ.get("MEDIATRANX_NCNN_SMOKE_ROOT"):
        print("set MEDIATRANX_NCNN_SMOKE_ROOT to the smoke root (bin/ncnn + models/)")
        return 2
    root = Path(os.environ["MEDIATRANX_NCNN_SMOKE_ROOT"])
    from app.init.configs import SETTINGS
    SETTINGS.path.root = root
    SETTINGS.path.models = root / "models"

    (OUT / "ab").mkdir(parents=True, exist_ok=True)
    fixtures = _fixtures()
    print(f"device={DEVICE}  fixtures={list(fixtures)}  out={OUT}\n")
    summary = []
    for family, variant, scale, url, member, cls in CASES:
        print(f"=== {family}/{variant} (x{scale}) ===")
        pth = _torch_pth(url, member, CACHE / f"{family}_{variant}.pth")
        ncnn_run = _ncnn_out(family, variant)
        for fx, img in fixtures.items():
            ref = _torch_ref(cls, pth, img, variant, scale).convert("RGB")
            out = ncnn_run(img).convert("RGB")
            ra, oa = np.asarray(ref), np.asarray(out)
            if oa.shape != ra.shape:    # guard against off-by-one resize
                out = out.resize(ref.size); oa = np.asarray(out)
            s, p = ssim(oa, ra), psnr(oa, ra)
            summary.append((f"{family}/{variant}", fx, s, p))
            print(f"  {fx:8s}  SSIM={s:.4f}  PSNR={p:6.2f}dB  shape={oa.shape}")
            # side-by-side A/B (torch | ncnn) for visual inspection
            ab = Image.new("RGB", (ref.width * 2 + 8, ref.height), (0, 0, 0))
            ab.paste(ref, (0, 0)); ab.paste(out, (ref.width + 8, 0))
            ab.save(OUT / "ab" / f"{family}_{variant}_{fx}_torchL_ncnnR.png")
        print()

    print("=== SUMMARY (NFR1 strict gate: SSIM>=0.99 & PSNR>=40dB) ===")
    for name, fx, s, p in summary:
        ok = "PASS" if (s >= 0.99 and p >= 40) else "below"
        print(f"  {name:24s} {fx:8s} SSIM={s:.4f} PSNR={p:6.2f}dB  [{ok}]")
    print(f"\nA/B images: {OUT / 'ab'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
