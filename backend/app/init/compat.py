"""
Third-party package compatibility patches.
"""
import sys
import types


def apply_compat_patches(settings) -> None:
    """Apply all compat patches."""
    _patch_torchvision_functional_tensor()
    _patch_scipy_signal_gaussian()


def _patch_torchvision_functional_tensor() -> None:
    try:
        import torchvision.transforms.functional_tensor  # noqa: F401
    except ImportError:
        try:
            import torchvision.transforms.functional as tvf
            compat = types.ModuleType("torchvision.transforms.functional_tensor")
            for attr in dir(tvf):
                setattr(compat, attr, getattr(tvf, attr))
            sys.modules["torchvision.transforms.functional_tensor"] = compat
        except ImportError:
            pass



def _patch_scipy_signal_gaussian() -> None:
    try:
        import scipy.signal
        if not hasattr(scipy.signal, 'gaussian'):
            from scipy.signal.windows import gaussian
            scipy.signal.gaussian = gaussian
    except ImportError:
        pass
