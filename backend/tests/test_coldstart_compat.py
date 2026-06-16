"""Cold-start guard: bootstrap() must NOT pull heavy AI libs onto the bind path.

The dominant ~5s of bind-blocking startup time was `apply_compat_patches()` in
bootstrap() force-loading torchvision (functional_tensor shim) + scipy.signal.
This guards that those imports stay off the bind path, and that the torchvision
compat shim is available (lazily) when actually needed.
"""
import builtins
import subprocess
import sys
import textwrap
from pathlib import Path

# backend/ root: this file is backend/tests/test_coldstart_compat.py
_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _run(code: str) -> str:
    """Run code in a CLEAN interpreter (this test process may already have torch)."""
    r = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True, text=True, cwd=str(_BACKEND_ROOT), timeout=120,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_bootstrap_does_not_load_heavy_modules():
    out = _run("""
        import sys
        from app.init import bootstrap
        bootstrap()
        heavy = [m for m in ("torch","torchvision","scipy.signal","scipy.stats") if m in sys.modules]
        print(",".join(heavy))
    """)
    assert out == "", f"bootstrap() pulled heavy modules onto the bind path: {out}"


def test_ensure_torchvision_compat_is_idempotent_and_makes_module_importable():
    out = _run("""
        from app.init.compat import ensure_torchvision_functional_tensor_compat as ensure
        ensure(); ensure()  # idempotent — second call must be a no-op, no error
        import torchvision.transforms.functional_tensor  # importable after the shim
        from torchvision.transforms.functional_tensor import rgb_to_grayscale  # symbol basicsr needs
        print("ok")
    """)
    assert out == "ok"


def test_importing_compat_module_does_not_load_torchvision():
    out = _run("""
        import sys
        import app.init.compat  # importing the module must NOT import torchvision
        print("torchvision" in sys.modules)
    """)
    assert out == "False"


def test_ensure_torchvision_compat_never_raises_on_broken_native_import(monkeypatch):
    """On weak/broken-GPU target machines `import torchvision` fails via torch's
    native-DLL load with OSError ([WinError 126]) / RuntimeError, not ImportError.
    ensure_...() is the first torchvision touch on the model-load path and must
    never raise (so the downstream `import spandrel` surfaces the real error)."""
    import app.init.compat as compat
    monkeypatch.setattr(compat, "_tv_compat_applied", False)  # reset run-once flag
    real_import = builtins.__import__

    def boom(name, *args, **kwargs):
        if name.startswith("torchvision"):
            raise OSError("[WinError 126] simulated broken native torch/torchvision")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", boom)
    # Must NOT raise (would raise OSError if the except clauses were `ImportError`).
    compat.ensure_torchvision_functional_tensor_compat()
