"""WS2 Task 3: wrappers get _model_manager attached at construction (build-then-
attach factory, replacing the eager loop), and llm is registered lazily (provider,
not eager instance) so torch stays off the bind path.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

_WRAPPER_PROVIDERS = (
    "whisper_wrapper", "demucs_wrapper", "alignment_engine",
    "basic_pitch_wrapper", "mobilesam_wrapper", "rife_wrapper",
    "realesrgan_wrapper", "swinir_wrapper", "bsrgan_wrapper",
    "real_cugan_wrapper", "waifu2x_wrapper", "gfpgan_wrapper",
    "llama_runtime",
)


def test_wrappers_get_model_manager_attached_at_construction():
    from app.init.container import init_container
    c = init_container()
    mm = c.model_manager()
    # Freshly resolve each wrapper via DI; each must already have _model_manager
    # set (build-then-attach factory), WITHOUT going through mm.acquire().
    for name in _WRAPPER_PROVIDERS:
        w = getattr(c, name)()
        assert w._model_manager is mm, f"{name} missing _model_manager at construction"


def test_llm_registered_lazily_not_constructed_eagerly():
    # In a clean interpreter, init_container must NOT construct LlmWrapper
    # (which would pull torch via base.py). _runtimes['llm'] stays empty until
    # first acquire; only the provider is registered.
    r = subprocess.run(
        [sys.executable, "-c", textwrap.dedent("""
            from app.init import bootstrap; bootstrap()
            from app.init.container import init_container
            c = init_container(); mm = c.model_manager()
            print("llm" in mm._runtimes)           # False — lazy provider, not eager instance
            print("llm" in mm._runtime_providers)   # True — provider registered for acquire()
        """)],
        capture_output=True, text=True, cwd=str(_BACKEND_ROOT), timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["False", "True"], r.stdout
