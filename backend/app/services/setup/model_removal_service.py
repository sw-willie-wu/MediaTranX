"""
Model removal service.
Handles deletion of downloaded model/tool files.
"""
import logging
import shutil

from pathlib import Path
from app.init.configs import SETTINGS

logger = logging.getLogger(__name__)


def _models_dir(category: str = "") -> Path:
    d = SETTINGS.path.models
    return d / category if category else d


def _match_ncnn_family(item_id: str):
    """Longest-prefix family match against the FORMAT_NCNN tree so an id like
    `realesrgan-x4plus-anime` resolves to family `realesrgan`, variant
    `x4plus-anime`. The current NCNN families (realesrgan/waifu2x) have no hyphen
    in the family name; longest-prefix is kept defensively (the PTH else-branch's
    split('-', 1) below would mis-split a future hyphenated family). Returns
    (family, variant) or None.
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


def remove_model(item_id: str, model_manager) -> None:
    """Delete downloaded model/tool files."""
    from app.adapters.ai.registry import SOUNDFONT_ID
    if item_id.startswith("whisper-"):
        size = item_id[len("whisper-"):]
        model_dir = _models_dir("whisper") / size
        if model_dir.exists():
            shutil.rmtree(model_dir)
            logger.info(f"Removed whisper model: {size}")

    elif item_id.startswith("qwen3-"):
        parts = item_id.split("-", 2)
        size, quant = parts[1], parts[2]
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

        qwen3_config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get("qwen3", {})
        specs = qwen3_config.get("specs", {})
        variant = specs.get(size, {}).get("variants", {}).get(quant)

        if variant:
            p = _models_dir("qwen3") / variant["filename"]
            if p.exists():
                p.unlink()
                logger.info(f"Removed qwen3 model: {item_id}")

    elif item_id.startswith(("qwen3vl-", "internvl2.5-", "gemma3-", "qwen3.5-")):
        # GGUF vision models: qwen3vl-4b-Q4_K_M
        parts = item_id.rsplit("-", 1)
        quant = parts[1]
        family_size = parts[0]
        size_parts = family_size.rsplit("-", 1)
        model_family = size_parts[0]
        size = size_parts[1]

        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_GGUF
        config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get(model_family, {})
        variant = config.get("specs", {}).get(size, {}).get("variants", {}).get(quant)
        if variant:
            target_dir = _models_dir() / model_family
            for fname in [variant.get("filename"), variant.get("mmproj_filename")]:
                if fname:
                    p = target_dir / fname
                    if p.exists():
                        p.unlink()
                        logger.info(f"Removed GGUF file: {fname}")

    elif item_id.startswith("demucs-"):
        # Demucs: models/demucs/checkpoints/*.th
        checkpoints_dir = _models_dir("demucs") / "checkpoints"
        if checkpoints_dir.exists():
            shutil.rmtree(checkpoints_dir)
            logger.info(f"Removed demucs checkpoints: {item_id}")

    elif item_id.startswith("rife-"):
        # RIFE: models/rife/flownet-*.pkl
        variant_name = item_id[len("rife-"):]
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_RIFE
        rife_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("rife", {})
        variant_spec = rife_config.get("variants", {}).get(variant_name)
        if variant_spec:
            p = _models_dir(SLOT_RIFE) / variant_spec.get("filename", "")
            if p.exists():
                p.unlink()
                logger.info(f"Removed rife model: {item_id}")

    elif item_id == SOUNDFONT_ID:
        sf_dir = SETTINGS.path.soundfonts
        if sf_dir.exists():
            shutil.rmtree(sf_dir)
            logger.info("Removed MusyngKite soundfont")

    else:
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_NCNN, FORMAT_PTH

        # SR families re-hosted as ncnn (.param/.bin pairs) are matched FIRST via
        # longest-prefix (realesrgan/waifu2x). Delete the pair, then prune the
        # variant dir (a cli_model_subdir like waifu2x/models-cunet) and the slot
        # dir, each only when left empty.
        ncnn_match = _match_ncnn_family(item_id)
        if ncnn_match:
            from app.adapters.ai.registry import ncnn_variant_dir
            family, variant = ncnn_match
            family_spec = MODELS_REGISTRY[FORMAT_NCNN][family]
            variant_spec = family_spec.get("variants", {}).get(variant)
            if variant_spec:
                slot = family_spec.get("slot", "")
                slot_dir = _models_dir(slot)
                vdir = ncnn_variant_dir(_models_dir(""), slot, variant_spec)
                for fname in variant_spec.get("files", []):
                    p = vdir / fname
                    if p.exists():
                        p.unlink()
                        logger.info(f"Removed ncnn file: {fname}")
                for d in dict.fromkeys([vdir, slot_dir]):   # subdir then slot, deduped
                    if d.exists() and not any(d.iterdir()):
                        d.rmdir()
            return

        # PTH models (upscale / face_restore): {family}-{variant}
        # Decompose ID: family-variant
        if '-' in item_id:
            family, variant = item_id.split('-', 1)
        else:
            family = item_id
            variant = None

        pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})
        model_config = pth_models.get(family)

        if model_config:
            if variant:
                variant_spec = model_config.get("variants", {}).get(variant)
                if variant_spec:
                    model_path = model_manager.get_model_path(family, variant)
                    if model_path and model_path.exists():
                        model_path.unlink()
                        logger.info(f"Removed PTH model: {item_id}")
            else:
                variants = model_config.get("variants", {})
                if variants:
                    first_variant = list(variants.keys())[0]
                    model_path = model_manager.get_model_path(family, first_variant)
                    if model_path and model_path.exists():
                        model_path.unlink()
                        logger.info(f"Removed PTH model: {family}")
