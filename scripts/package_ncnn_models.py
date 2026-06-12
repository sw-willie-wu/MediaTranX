# scripts/package_ncnn_models.py
"""Extract the ncnn SR model pairs we re-host from the official upstream zips.

Downloads the three pinned upstream release zips, pulls exactly the canonical
.param/.bin pairs Phase 1 ships, plus:
  - each zip's own LICENSE/README (covers the ncnn CLI *code*, MIT), and
  - the authoritative license for the *weights* we actually redistribute —
    the obligation the zip texts do NOT satisfy (the realesrgan zip ships only
    a README, no LICENSE; its weights are BSD-3 from xinntao/Real-ESRGAN).
Real-CUGAN's weights (bilibili/ailab) carry NO upstream license; we cannot
bundle one, so we emit an explicit provenance NOTICE that records the R6
re-hosting decision in the release itself.
Writes ./ncnn-models/ + manifest.json (per-file byte sizes, for registry
size_mb). Upload EVERYTHING to release tag `ncnn-models-v1`.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

UPSTREAM = {
    "realesrgan": (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
        "realesrgan-ncnn-vulkan-20220424-windows.zip",
        ["models/realesrgan-x4plus", "models/realesrgan-x4plus-anime",
         "models/realesr-animevideov3-x2", "models/realesr-animevideov3-x3",
         "models/realesr-animevideov3-x4"],
    ),
    "waifu2x": (
        "https://github.com/nihui/waifu2x-ncnn-vulkan/releases/download/20250915/"
        "waifu2x-ncnn-vulkan-20250915-windows.zip",
        ["models-cunet/scale2.0x_model"],
    ),
    "realcugan": (
        "https://github.com/nihui/realcugan-ncnn-vulkan/releases/download/20220728/"
        "realcugan-ncnn-vulkan-20220728-windows.zip",
        ["models-se/up2x-conservative", "models-se/up3x-conservative",
         "models-se/up4x-conservative"],
    ),
}

# Authoritative license for the WEIGHTS (model checkpoints) we redistribute,
# distinct from the ncnn CLI code license bundled inside each zip. Verified via
# the GitHub license API (2026-06-12).
WEIGHTS_LICENSE_URL = {
    "realesrgan": "https://raw.githubusercontent.com/xinntao/Real-ESRGAN/master/LICENSE",  # BSD-3
    "waifu2x": "https://raw.githubusercontent.com/nagadomi/waifu2x/master/LICENSE",         # MIT
    # realcugan: bilibili/ailab carries no license — see REALCUGAN_NOTICE below.
}

REALCUGAN_NOTICE = (
    "Real-CUGAN weights provenance NOTICE\n"
    "====================================\n"
    "The up{2,3,4}x-conservative .param/.bin files are the ncnn conversion\n"
    "(nihui/realcugan-ncnn-vulkan, MIT *code*) of the Real-CUGAN checkpoints\n"
    "from bilibili/ailab (https://github.com/bilibili/ailab). The upstream\n"
    "weights repository carries NO license file; redistribution terms are\n"
    "unspecified by the original author. Re-hosting these files on the\n"
    "MediaTranX release is a deliberate decision recorded here for the R6\n"
    "review (see plan D-P1-2).\n"
)


def main() -> int:
    out = Path("ncnn-models"); out.mkdir(exist_ok=True)
    manifest: dict[str, dict] = {}
    for tool, (url, stems) in UPSTREAM.items():
        print(f"downloading {url} ...")
        data = urllib.request.urlopen(url).read()
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        wanted = [(stem, ext) for stem in stems for ext in (".param", ".bin")]
        for stem, ext in wanted:
            match = [n for n in names if n.endswith(f"{stem}{ext}")]
            if len(match) != 1:
                print(f"ERROR: {tool} {stem}{ext}: {len(match)} matches"); return 1
            blob = zf.read(match[0])
            fname = Path(stem).name + ext
            (out / fname).write_bytes(blob)
            manifest[fname] = {"tool": tool, "bytes": len(blob)}
            print(f"  {fname}: {len(blob):,} bytes")
        # Bonus attribution: the zip's own LICENSE/README (ncnn CLI code).
        for n in names:
            base = Path(n).name.lower()
            if base.startswith(("license", "readme")) and not n.endswith("/"):
                (out / f"{tool}-{Path(n).name}").write_bytes(zf.read(n))

    # The obligation that actually matters: the WEIGHTS license.
    for tool, lic_url in WEIGHTS_LICENSE_URL.items():
        print(f"fetching {tool} weights license: {lic_url}")
        text = urllib.request.urlopen(lic_url).read()
        if not text.strip():
            print(f"ERROR: {tool} weights license fetched empty"); return 1
        (out / f"{tool}-WEIGHTS-LICENSE.txt").write_bytes(text)
    (out / "realcugan-WEIGHTS-NOTICE.txt").write_text(REALCUGAN_NOTICE, encoding="utf-8")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote {len(manifest)} model files + weights licenses to {out}/.")
    print("R6: realesrgan weights = BSD-3 (bundled), waifu2x = MIT (bundled), "
          "realcugan = UNLICENSED bilibili weights (NOTICE only — needs sign-off).")
    print("Upload ALL contents to release tag 'ncnn-models-v1' of sw-willie-wu/MediaTranX.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
