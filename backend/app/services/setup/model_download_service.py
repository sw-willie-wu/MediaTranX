"""
Model download service.
Handles downloading models in various formats: Whisper (BIN), GGUF, PTH.
"""
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from app.init.configs import SETTINGS

logger = logging.getLogger(__name__)


def _models_dir(category: str = "") -> Path:
    """Get models directory with optional category subdirectory, ensuring it exists."""
    d = SETTINGS.path.models
    if category:
        d = d / category
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- Public interface ---

def handle_model_download(params: dict, progress_callback: Callable[[float, str], None]) -> dict:
    """
    Model/tool download task handler (synchronous).
    Called by TaskManager's Executor.
    """
    item_id = params.get("id", "")
    logger.info(f"Starting model download: {item_id}")
    progress_callback(0.05, f"task.progress.download_preparing|{item_id}")

    from app.adapters.ai.registry import SOUNDFONT_ID

    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        raise RuntimeError("huggingface_hub not installed; please install the base environment first")

    if item_id.startswith("whisper-"):
        size = item_id[len("whisper-"):]
        _download_whisper(size, progress_callback, snapshot_download)

    elif item_id.startswith(("qwen3-", "qwen3vl-", "internvl2.5-", "gemma3-", "gemma4-", "qwen3.5-")):
        # Parse: {family}-{size}-{quant}
        parts = item_id.rsplit("-", 1)
        quant = parts[1]
        family_size = parts[0].rsplit("-", 1)
        model_family = family_size[0]
        size = family_size[1]
        _download_gguf(model_family, size, quant, progress_callback)

    elif item_id.startswith("demucs-"):
        variant = item_id[len("demucs-"):]
        _download_demucs(variant, progress_callback)

    elif item_id.startswith("alignment-"):
        lang_code = item_id[len("alignment-"):]
        _download_alignment(lang_code, progress_callback)

    elif item_id.startswith("rife-"):
        variant = item_id[len("rife-"):]
        _download_rife(variant, progress_callback)

    elif item_id == "basic-pitch":
        _download_basic_pitch(progress_callback)

    elif item_id == SOUNDFONT_ID:
        _download_soundfont(progress_callback)

    else:
        # SR families re-hosted as ncnn (.param/.bin pairs) route here FIRST via
        # longest-prefix family match; everything else is a PTH model.
        ncnn_match = _match_ncnn_family(item_id)
        if ncnn_match:
            _download_ncnn(ncnn_match[0], ncnn_match[1], progress_callback)
        else:
            _download_pth_model(item_id, progress_callback)

    progress_callback(1.0, "task.progress.download_complete")
    return {"status": "ok", "id": item_id}


# --- Common download utilities ---

def _download_from_url(
    url: str,
    target_path: Path,
    progress_callback: Callable[[float, str], None],
    base_progress: float = 0.1,
    end_progress: float = 0.95,
) -> None:
    """Download file from direct URL (supports GitHub releases, etc.)."""
    import requests

    target_path.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, stream=True, allow_redirects=True, timeout=60)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 4 * 1024 * 1024

    with open(target_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    frac = downloaded / total
                    prog = base_progress + frac * (end_progress - base_progress)
                    mb_done = downloaded / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    progress_callback(prog, f"task.progress.downloading_mb|{mb_done:.0f}|{mb_total:.0f}")

    if target_path.exists():
        size_mb = target_path.stat().st_size / 1024 / 1024
        progress_callback(end_progress, f"task.progress.download_done_mb|{size_mb:.1f}")


def _stream_download(
    repo_id: str,
    filename: str,
    target_path: Path,
    progress_callback: Callable[[float, str], None],
    base_progress: float = 0.1,
    end_progress: float = 0.95,
) -> None:
    """Download a single file via HuggingFace Hub with real-time progress reporting."""
    from huggingface_hub import hf_hub_url

    try:
        url = hf_hub_url(repo_id=repo_id, filename=filename)
        logger.info(f"Resolved HF URL for {filename}: {url}")
        _download_from_url(
            url=url,
            target_path=target_path,
            progress_callback=progress_callback,
            base_progress=base_progress,
            end_progress=end_progress,
        )
    except Exception as e:
        logger.error(f"Streaming download failed for {filename}: {e}")
        raise RuntimeError(f"Download failed ({filename}): {str(e)}")


# --- Format-specific downloaders ---

def _match_ncnn_family(item_id: str):
    """Longest-prefix family match against the FORMAT_NCNN tree so an id like
    `realesrgan-x4plus-anime` resolves to family `realesrgan`, variant
    `x4plus-anime`. The current NCNN families (realesrgan/waifu2x) have no hyphen
    in the family name, but longest-prefix is kept defensively and to mirror the
    PTH idiom in _download_pth_model (where hyphenated family names exist).
    Returns (family, variant) or None.
    """
    from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_NCNN

    ncnn_models = MODELS_REGISTRY.get(FORMAT_NCNN, {})
    matched = [
        (family_name, item_id[len(family_name) + 1:])
        for family_name in ncnn_models
        if item_id.startswith(family_name + "-")
    ]
    if not matched:
        return None
    return max(matched, key=lambda x: len(x[0]))


def _download_ncnn(family: str, variant: str, progress_callback: Callable[[float, str], None]) -> None:
    """Download an ncnn-vulkan SR model's .param+.bin pair from our re-host
    release (the shared `vendored-deps` tag) into models/<slot>/. Skips files
    already on disk
    (same skip-if-exists semantics as _download_demucs / _download_rife; the PTH
    path has no skip, so do not cite it).
    """
    from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_NCNN, _NCNN_BASE_URL

    family_spec = MODELS_REGISTRY.get(FORMAT_NCNN, {}).get(family)
    if not family_spec:
        raise ValueError(f"Unknown ncnn model family: {family}")
    variant_spec = family_spec.get("variants", {}).get(variant)
    if not variant_spec:
        raise ValueError(f"Unknown ncnn model variant: {family}-{variant}")

    slot = family_spec.get("slot", "")
    if not slot:
        raise ValueError(f"ncnn model {family} missing slot configuration")

    target_dir = _models_dir(slot)
    files = variant_spec["files"]
    n = len(files)
    span_lo, span_hi = 0.1, 0.95
    for i, fname in enumerate(files):
        target_path = target_dir / fname
        if target_path.exists():
            continue                       # skip-if-exists (no byte check)
        base = span_lo + (span_hi - span_lo) * (i / n)
        end = span_lo + (span_hi - span_lo) * ((i + 1) / n)
        progress_callback(base, f"task.progress.downloading_variant|{family}|{variant}")
        url = f"{_NCNN_BASE_URL}/{fname}"
        _download_from_url(url, target_path, progress_callback, base_progress=base, end_progress=end)


def _download_whisper(size: str, progress_callback: Callable[[float, str], None], snapshot_download) -> None:
    from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PKG

    whisper_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("whisper", {})
    variants = whisper_config.get("variants", {})
    variant_spec = variants.get(size)

    if not variant_spec:
        raise ValueError(f"Unknown Whisper model size: {size}")

    repo_id = variant_spec["repo_id"]
    local_dir = _models_dir("whisper") / size
    local_dir.mkdir(parents=True, exist_ok=True)

    model_bin = local_dir / "model.bin"
    if not model_bin.exists():
        progress_callback(0.1, f"task.progress.downloading_whisper|{size}")
        _stream_download(repo_id, "model.bin", model_bin, progress_callback, 0.1, 0.9)

    progress_callback(0.9, "task.progress.downloading_tokenizer")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        ignore_patterns=["*.md", "model.bin", "model.safetensors"],
    )
    progress_callback(0.98, "task.progress.model_verified")


def _download_gguf(model_family: str, size: str, quant: str, progress_callback: Callable[[float, str], None]) -> None:
    """Download GGUF model (including mmproj for vision models)."""
    from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

    config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get(model_family, {})
    specs = config.get("specs", {})
    variant = specs.get(size, {}).get("variants", {}).get(quant)

    if not variant:
        raise ValueError(f"Unknown model variant: {model_family}-{size}-{quant}")

    target_dir = _models_dir(model_family)
    target_dir.mkdir(parents=True, exist_ok=True)

    has_mmproj = "mmproj_filename" in variant

    progress_callback(0.05, f"task.progress.downloading_model|{model_family}|{size}|{quant}")
    _stream_download(
        repo_id=variant["repo_id"],
        filename=variant["filename"],
        target_path=target_dir / variant["filename"],
        progress_callback=progress_callback,
        base_progress=0.05,
        end_progress=0.65 if has_mmproj else 0.95,
    )

    if has_mmproj:
        progress_callback(0.65, "task.progress.downloading_mmproj")
        # mmproj_remote_filename: actual filename on HuggingFace (may differ from local name)
        remote_mmproj = variant.get("mmproj_remote_filename", variant["mmproj_filename"])
        _stream_download(
            repo_id=variant.get("mmproj_repo_id", variant["repo_id"]),
            filename=remote_mmproj,
            target_path=target_dir / variant["mmproj_filename"],
            progress_callback=progress_callback,
            base_progress=0.65,
            end_progress=0.95,
        )

    progress_callback(0.95, "task.progress.model_download_complete")


def _download_demucs(variant: str, progress_callback: Callable[[float, str], None]) -> None:
    """Download Demucs model checkpoint (direct from Facebook, avoids demucs package path issues)."""
    from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_DEMUCS

    family = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("demucs")
    if not family:
        raise ValueError("demucs not registered in registry")

    variant_spec = family["variants"].get(variant)
    if not variant_spec:
        raise ValueError(f"Unknown demucs variant: {variant}")

    model_name = variant_spec.get("model_name", variant)
    progress_callback(0.1, f"task.progress.downloading_named|{model_name}")

    # Model hash -> checkpoint filename mapping (from demucs/remote/*.yaml + files.txt)
    DEMUCS_MODELS = {
        "htdemucs": ("hybrid_transformer", "955717e8-8726e21a.th"),
        "htdemucs_6s": ("hybrid_transformer", "5c90dfd2-34c22ccb.th"),
    }

    if model_name not in DEMUCS_MODELS:
        raise ValueError(f"Unsupported demucs model: {model_name}")

    folder, filename = DEMUCS_MODELS[model_name]
    url = f"https://dl.fbaipublicfiles.com/demucs/{folder}/{filename}"

    checkpoints_dir = _models_dir() / SLOT_DEMUCS / "checkpoints"
    target_path = checkpoints_dir / filename

    if target_path.exists():
        progress_callback(0.95, "task.progress.model_exists")
        return

    progress_callback(0.15, f"task.progress.downloading_checkpoint|{model_name}")
    _download_from_url(url, target_path, progress_callback, 0.15, 0.95)
    progress_callback(0.95, "task.progress.model_download_complete")


def _download_rife(variant: str, progress_callback: Callable[[float, str], None]) -> None:
    """Download RIFE model checkpoint (extracts flownet.pkl from zip)"""
    import io
    import zipfile
    from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_RIFE

    family = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("rife")
    if not family:
        raise ValueError("rife not registered")

    variant_spec = family["variants"].get(variant)
    if not variant_spec:
        raise ValueError(f"Unknown RIFE variant: {variant}")

    url = variant_spec["url"]
    filename = variant_spec["filename"]
    zip_entry = variant_spec.get("zip_entry", "")

    target_dir = _models_dir() / SLOT_RIFE
    target_path = target_dir / filename

    if target_path.exists():
        progress_callback(0.95, "task.progress.model_exists")
        return

    import tempfile
    progress_callback(0.1, f"task.progress.downloading_rife|{variant}")

    # Download zip to temp, extract flownet.pkl
    tmp_zip = Path(tempfile.mktemp(suffix=".zip"))
    try:
        _download_from_url(url, tmp_zip, progress_callback, 0.1, 0.80)
        progress_callback(0.85, "task.progress.extracting_model")

        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            # Find flownet.pkl in zip
            pkl_name = zip_entry or next(
                (n for n in zf.namelist() if n.endswith("flownet.pkl")), None
            )
            if not pkl_name:
                raise RuntimeError("flownet.pkl not found in zip")
            data = zf.read(pkl_name)
            target_path.write_bytes(data)
            logger.info(f"Extracted {pkl_name} → {target_path} ({len(data)} bytes)")
    finally:
        tmp_zip.unlink(missing_ok=True)

    progress_callback(0.95, "task.progress.model_download_complete")


def _download_alignment(lang_code: str, progress_callback: Callable[[float, str], None]) -> None:
    """Download Wav2Vec2 alignment model (via transformers from HuggingFace)."""
    from app.adapters.ai.wrapper.wav2vec2 import LANG_MODELS

    if lang_code not in LANG_MODELS:
        raise ValueError(f"Unsupported language: {lang_code}")

    repo_id = LANG_MODELS[lang_code]
    cache_dir = str(_models_dir("alignment"))
    progress_callback(0.1, f"task.progress.downloading_repo|{repo_id}")

    try:
        from huggingface_hub import list_repo_files, hf_hub_download

        # List files in the repo
        all_files = list_repo_files(repo_id)
        download_files = [
            f for f in all_files
            if not f.endswith((".md", ".txt", ".gitattributes"))
        ]

        if not download_files:
            raise RuntimeError(f"No downloadable files in repo {repo_id}")

        total = len(download_files)
        for i, filename in enumerate(download_files):
            prog = 0.1 + (i / total) * 0.85  # 0.1 ~ 0.95
            progress_callback(prog, f"task.progress.downloading_file|{filename}|{i + 1}|{total}")
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=cache_dir,
            )

    except Exception as e:
        raise RuntimeError(f"Alignment model download failed: {e}")

    progress_callback(0.95, "task.progress.model_download_complete")


def _download_pth_model(model_id: str, progress_callback: Callable[[float, str], None]) -> None:
    """Download PTH model (upscale / face_restore)."""
    from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PTH

    pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})

    # Smart ID decomposition: try matching all families (handles multi-hyphen cases like real-cugan)
    family = None
    variant = None

    matched_families = [
        (family_name, model_id[len(family_name) + 1:])
        for family_name in pth_models.keys()
        if model_id.startswith(family_name + "-")
    ]

    if matched_families:
        family, variant = max(matched_families, key=lambda x: len(x[0]))

    if not family or not variant:
        raise ValueError(f"Invalid model ID format: {model_id}, cannot match any known model family")

    model_config = pth_models.get(family)

    if not model_config:
        raise ValueError(f"Unknown model family: {family}")

    variant_spec = model_config.get("variants", {}).get(variant)
    if not variant_spec:
        raise ValueError(f"Unknown model variant: {family}-{variant}")

    slot = model_config.get("slot", "")
    if not slot:
        raise ValueError(f"Model {family} missing slot configuration")

    target_dir = _models_dir() / slot
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = variant_spec["filename"]
    target_path = target_dir / filename

    needs_unzip = variant_spec.get("unzip", False)
    archive_path = variant_spec.get("archive_path", None)

    if "url" in variant_spec:
        url = variant_spec["url"]
        progress_callback(0.1, f"task.progress.downloading_variant|{family}|{variant}")

        if needs_unzip:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_archive = Path(temp_dir) / "archive.zip"
                _download_from_url(url, temp_archive, progress_callback, 0.1, 0.85)

                progress_callback(0.85, "task.progress.decompressing")

                with zipfile.ZipFile(temp_archive, 'r') as zip_ref:
                    if archive_path:
                        all_files = zip_ref.namelist()

                        matching_files = []
                        if archive_path in all_files:
                            matching_files = [archive_path]
                        else:
                            matching_files = [
                                name for name in all_files
                                if name.endswith(archive_path) or name.endswith('/' + archive_path)
                            ]
                            if not matching_files:
                                target_basename = Path(archive_path).name
                                matching_files = [
                                    name for name in all_files
                                    if Path(name).name == target_basename
                                ]

                        if not matching_files:
                            files_list = "\n  ".join(all_files[:10])
                            raise ValueError(
                                f"File not found in archive: {archive_path}\n"
                                f"Archive contains {len(all_files)} files, first few:\n  {files_list}"
                            )

                        source_file = matching_files[0]
                        temp_extract = Path(temp_dir) / "extracted"
                        zip_ref.extract(source_file, temp_extract)
                        extracted_file = temp_extract / source_file
                        shutil.copy2(extracted_file, target_path)
                    else:
                        zip_ref.extractall(target_dir)

                progress_callback(0.95, "task.progress.decompression_complete")
        else:
            _download_from_url(url, target_path, progress_callback, 0.1, 0.95)
    elif "repo_id" in variant_spec:
        repo_id = variant_spec["repo_id"]
        progress_callback(0.1, f"task.progress.downloading_variant|{family}|{variant}")
        _stream_download(
            repo_id=repo_id,
            filename=filename,
            target_path=target_path,
            progress_callback=progress_callback,
            base_progress=0.1,
            end_progress=0.95,
        )
    else:
        raise ValueError(f"Model {family}-{variant} missing url or repo_id configuration")

    progress_callback(0.95, "task.progress.model_download_complete")


def _download_basic_pitch(progress_callback: Callable[[float, str], None]) -> None:
    """Trigger basic-pitch model download by running a dummy inference."""
    # Lazy import: soundfile carries libsndfile native libs. Keep it (and numpy,
    # only used here) out of module top level — this module is imported eagerly
    # at startup via container -> SetupService, so a broken dependency must not
    # crash backend startup, only this download.
    import numpy as np
    import soundfile as sf

    progress_callback(0.1, "task.progress.downloading_basic_pitch")

    # Create a tiny silent audio file to trigger model auto-download
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            sf.write(tmp_path, np.zeros(44100, dtype=np.float32), 44100)

        progress_callback(0.3, "task.progress.loading_basic_pitch")
        from basic_pitch.inference import predict

        try:
            predict(tmp_path)
        except Exception:
            pass  # May fail on silent audio, but model is now cached

        import os

        os.unlink(tmp_path)
    except Exception as e:
        logger.warning(f"Basic Pitch download trigger failed: {e}")
        raise

    progress_callback(0.95, "task.progress.basic_pitch_ready")


def _soundfont_instruments() -> list[str]:
    """回 GM 樂器清單（獨立函式，方便測試只跑 1 個樂器）。"""
    from app.adapters.ai.registry import GM_INSTRUMENTS
    return GM_INSTRUMENTS


def _download_soundfont(progress_callback: Callable[[float, str], None]) -> None:
    """Download MusyngKite GM soundfont (移植自 electron/setup.js downloadSoundfonts).

    樂器佔進度 0.0–0.9、鼓組佔 0.9–1.0（鼓組在樂器後跑，避免提早 100%）。
    單檔失敗 warn 後續跑，不整批中斷。
    """
    import base64
    import json
    import re
    import requests
    from app.adapters.ai.registry import (
        SOUNDFONT_BASE_URL, SOUNDFONT_DRUM_BASE_URL, SOUNDFONT_VERSION_TAG,
    )

    sf_dir = SETTINGS.path.soundfonts
    sf_dir.mkdir(parents=True, exist_ok=True)

    note_re = re.compile(r'''["']([A-G][b#]?\d)["']\s*:\s*["']data:audio/mp3;base64,([^"']+)["']''')
    instruments = _soundfont_instruments()
    total = len(instruments)

    for i, instrument in enumerate(instruments):
        progress_callback(i / total * 0.9, f"task.progress.downloading_soundfont|{i + 1}|{total}")
        url = f"{SOUNDFONT_BASE_URL}/{instrument}-mp3.js"
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            text = resp.text
            inst_dir = sf_dir / f"{instrument}-mp3"
            inst_dir.mkdir(parents=True, exist_ok=True)
            for note, b64 in note_re.findall(text):
                (inst_dir / f"{note}.mp3").write_bytes(base64.b64decode(b64.strip()))
        except Exception as e:
            logger.warning(f"[soundfont] failed {instrument}: {e}")

    # Drum kit (notes 35-81) from WebAudioFont
    progress_callback(0.9, "task.progress.downloading_soundfont_drums")
    drum_dir = sf_dir / "drums-mp3"
    drum_dir.mkdir(parents=True, exist_ok=True)
    file_re = re.compile(r"file\s*:\s*'([A-Za-z0-9+/=]+)'")
    for note in range(35, 82):
        url = f"{SOUNDFONT_DRUM_BASE_URL}/128{note}_0_FluidR3_GM_sf2_file.js"
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            text = resp.text
            m = file_re.search(text)
            if m:
                (drum_dir / f"{note}.mp3").write_bytes(base64.b64decode(m.group(1)))
        except Exception as e:
            logger.warning(f"[soundfont] failed drum {note}: {e}")

    (sf_dir / ".version").write_text(json.dumps({"tag": SOUNDFONT_VERSION_TAG}), encoding="utf-8")
