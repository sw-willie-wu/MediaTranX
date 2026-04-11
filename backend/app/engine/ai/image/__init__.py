"""Image AI engine wrappers. Import from specific modules directly."""


def get_upscaler(model_id: str):
    """
    Get the corresponding upscale wrapper by model_id (lazy import).

    Args:
        model_id: Model family ID (realesrgan/swinir/bsrgan/real-cugan/waifu2x).

    Returns:
        The corresponding wrapper instance.
    """
    if model_id == "realesrgan":
        from .realesrgan import get_realesrgan
        return get_realesrgan()
    elif model_id == "swinir":
        from .swinir import get_swinir
        return get_swinir()
    elif model_id == "bsrgan":
        from .bsrgan import get_bsrgan
        return get_bsrgan()
    elif model_id == "real-cugan":
        from .real_cugan import get_real_cugan
        return get_real_cugan()
    elif model_id == "waifu2x":
        from .waifu2x import get_waifu2x
        return get_waifu2x()
    else:
        available = ["realesrgan", "swinir", "bsrgan", "real-cugan", "waifu2x"]
        raise ValueError(f"Unknown upscale model: {model_id}. Available: {available}")


def get_face_restorer(model_id: str):
    """
    Get the corresponding face restoration wrapper by model_id (lazy import).

    Args:
        model_id: Model family ID (codeformer/gfpgan).

    Returns:
        The corresponding wrapper instance.
    """
    if model_id == "codeformer":
        from .codeformer import get_codeformer
        return get_codeformer()
    elif model_id == "gfpgan":
        from .gfpgan import get_gfpgan
        return get_gfpgan()
    else:
        available = ["codeformer", "gfpgan"]
        raise ValueError(f"Unknown face_restore model: {model_id}. Available: {available}")
