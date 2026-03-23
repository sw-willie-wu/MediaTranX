"""
第三方套件相容層
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
處理 torchvision 等套件的 API 變動相容問題。
必須在 sys.path 注入後執行。
"""
import sys
import types


def apply_compat_patches() -> None:
    """套用所有相容性修補"""
    _patch_torchvision_functional_tensor()


def _patch_torchvision_functional_tensor() -> None:
    """
    torchvision >= 0.16 移除了 functional_tensor 模組，
    但 basicsr/realesrgan 仍會 import 它。
    建立一個 shim 模組指向 functional。
    """
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
            pass  # torchvision 尚未安裝，跳過
