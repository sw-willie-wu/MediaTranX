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
    _patch_pyfluidsynth_dll_dir()
    _patch_scipy_signal_gaussian()


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


def _patch_pyfluidsynth_dll_dir() -> None:
    """
    pyfluidsynth 在 import 時硬編碼 os.add_dll_directory('C:\\tools\\fluidsynth\\bin')，
    路徑不存在會直接 crash，連帶影響 pretty_midi 和 basic-pitch。
    預先建立該目錄避免 FileNotFoundError（僅 Windows）。
    """
    if sys.platform != "win32":
        return
    from pathlib import Path
    hardcoded = Path("C:/tools/fluidsynth/bin")
    if not hardcoded.exists():
        hardcoded.mkdir(parents=True, exist_ok=True)


def _patch_scipy_signal_gaussian() -> None:
    """
    scipy >= 1.12 移除了 scipy.signal.gaussian，
    但 basic-pitch 的 note_creation.py 仍直接呼叫 scipy.signal.gaussian()。
    將 scipy.signal.windows.gaussian 掛回 scipy.signal。
    """
    try:
        import scipy.signal
        if not hasattr(scipy.signal, 'gaussian'):
            from scipy.signal.windows import gaussian
            scipy.signal.gaussian = gaussian
    except ImportError:
        pass
