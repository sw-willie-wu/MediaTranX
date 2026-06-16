"""Third-party compatibility patches.

Applied LAZILY at point of use, NOT eagerly in bootstrap() — importing the
patched libraries (torchvision, scipy) is ~4 s and must stay off the
bind-blocking startup path. The only patch retained is the torchvision
functional_tensor shim, applied at the spandrel model-load chokepoint
(see PthWrapper._load_with_spandrel). The former scipy.signal.gaussian patch
was removed: its sole consumer (basic_pitch) self-patches at point of use
(see adapters/ai/wrapper/basic_pitch.py).
"""
import sys
import types

_tv_compat_applied = False


def ensure_torchvision_functional_tensor_compat() -> None:
    """Idempotent. Ensure ``torchvision.transforms.functional_tensor`` is
    importable. That public module was removed in torchvision >= 0.17, but
    basicsr (``basicsr/data/degradations.py``) still imports it. Call this
    immediately before any code that may import basicsr (e.g. before
    ``import spandrel``). Triggers the torchvision import only here — lazily,
    off the bind path. No-op when the first import succeeds (older torchvision).
    """
    global _tv_compat_applied
    if _tv_compat_applied:
        return
    _tv_compat_applied = True
    # Broad `except Exception` (not just ImportError): on weak/broken-GPU target
    # machines `import torchvision` fails via torch's native-DLL load with
    # OSError ([WinError 126]) / RuntimeError, not ImportError. This function is
    # now the FIRST torchvision touch on the model-load path, so it must never
    # raise — it swallows any failure here and lets the subsequent `import
    # spandrel` surface the real error with model-load context.
    try:
        import torchvision.transforms.functional_tensor  # noqa: F401
    except Exception:
        try:
            import torchvision.transforms.functional as tvf
            compat = types.ModuleType("torchvision.transforms.functional_tensor")
            for attr in dir(tvf):
                setattr(compat, attr, getattr(tvf, attr))
            sys.modules["torchvision.transforms.functional_tensor"] = compat
        except Exception:
            pass
