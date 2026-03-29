"""
Nuitka Frozen Mode 相容性修補
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nuitka 的 --nofollow-import-to 排除 AI 套件（torch, demucs 等）後，
runtime 匯入這些套件時 __file__ 可能指向 Nuitka 輸出目錄而非 .venv，
導致套件內的資料檔定位失敗。此模組統一修正這些問題。

僅在 frozen mode 執行，dev 環境完全不受影響。
"""
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def apply_nuitka_patches() -> None:
    """
    套用所有 Nuitka frozen mode 的相容性修補。
    由 bootstrap() 在 frozen mode 時呼叫。
    """
    _patch_torch_dynamo()
    _patch_demucs_remote_root()
    logger.info("Nuitka compatibility patches applied")


def _patch_torch_dynamo() -> None:
    """
    transformers 的 masking_utils 嘗試
    from torch._dynamo._trace_wrapped_higher_order_op import TransformGetItemToIndex
    在 Nuitka 環境下此 import 可能失敗。
    預先塞一個 no-op context manager 到 sys.modules 繞過。
    """
    key = "torch._dynamo._trace_wrapped_higher_order_op"
    if key in sys.modules:
        return
    try:
        from torch._dynamo._trace_wrapped_higher_order_op import TransformGetItemToIndex  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        import types
        import contextlib
        fake = types.ModuleType(key)
        fake.TransformGetItemToIndex = contextlib.nullcontext
        sys.modules[key] = fake
        logger.info(f"Patched {key} (fake context manager)")
    except Exception:
        pass  # torch 未安裝，跳過


def _patch_demucs_remote_root() -> None:
    """
    demucs.pretrained.REMOTE_ROOT = Path(__file__).parent / 'remote'
    在 Nuitka 環境下 __file__ 指向 core_service/demucs/，
    而非 .venv/site-packages/demucs/，導致 remote/files.txt 找不到。
    掃描 sys.path 找到正確路徑並覆蓋。
    """
    try:
        import demucs.pretrained as _pretrained
    except (ImportError, ModuleNotFoundError):
        return  # demucs 未安裝，跳過

    if _pretrained.REMOTE_ROOT.exists():
        return  # 路徑正確，不需修補

    for p in sys.path:
        candidate = Path(p) / "demucs" / "remote"
        if candidate.exists():
            _pretrained.REMOTE_ROOT = candidate
            logger.info(f"Patched demucs REMOTE_ROOT → {candidate}")
            return
