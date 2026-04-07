"""
模型移除服務
負責刪除已下載的模型/工具檔案。
"""
import logging
import shutil

from pathlib import Path
from app.init.configs import SETTINGS

logger = logging.getLogger(__name__)


def _models_dir(category: str = "") -> Path:
    d = SETTINGS.path.models
    return d / category if category else d


def remove_model(item_id: str) -> None:
    """刪除已下載的模型/工具檔案"""
    if item_id.startswith("whisper-"):
        size = item_id[len("whisper-"):]
        model_dir = _models_dir("whisper") / size
        if model_dir.exists():
            shutil.rmtree(model_dir)
            logger.info(f"Removed whisper model: {size}")

    elif item_id.startswith("translategemma-"):
        parts = item_id.split("-", 2)
        size, quant = parts[1], parts[2]
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

        translategemma_config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get("translategemma", {})
        specs = translategemma_config.get("specs", {})
        variant = specs.get(size, {}).get("variants", {}).get(quant)

        if variant:
            p = _models_dir("translategemma") / variant["filename"]
            if p.exists():
                p.unlink()
                logger.info(f"Removed translategemma model: {item_id}")

    elif item_id.startswith("qwen3-"):
        parts = item_id.split("-", 2)
        size, quant = parts[1], parts[2]
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

        qwen3_config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get("qwen3", {})
        specs = qwen3_config.get("specs", {})
        variant = specs.get(size, {}).get("variants", {}).get(quant)

        if variant:
            p = _models_dir("qwen3") / variant["filename"]
            if p.exists():
                p.unlink()
                logger.info(f"Removed qwen3 model: {item_id}")

    elif item_id.startswith(("qwen3vl-", "internvl2.5-", "gemma3-", "qwen3.5-")):
        # GGUF 視覺模型：qwen3vl-4b-Q4_K_M
        parts = item_id.rsplit("-", 1)
        quant = parts[1]
        family_size = parts[0]
        size_parts = family_size.rsplit("-", 1)
        model_family = size_parts[0]
        size = size_parts[1]

        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_GGUF
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

    else:
        # PTH 模型（upscale / face_restore）: {family}-{variant}
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PTH

        # 分解 ID: family-variant
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
                    from app.init.container import get_container
                    manager = get_container().model_manager()
                    model_path = manager.get_model_path(family, variant)
                    if model_path and model_path.exists():
                        model_path.unlink()
                        logger.info(f"Removed PTH model: {item_id}")
            else:
                variants = model_config.get("variants", {})
                if variants:
                    first_variant = list(variants.keys())[0]
                    from app.init.container import get_container
                    manager = get_container().model_manager()
                    model_path = manager.get_model_path(family, first_variant)
                    if model_path and model_path.exists():
                        model_path.unlink()
                        logger.info(f"Removed PTH model: {family}")
