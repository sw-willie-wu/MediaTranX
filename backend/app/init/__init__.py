"""
Application initialization — single entry point for all startup tasks.
"""
# 1. Inject .venv/site-packages (before any third-party import)
from app.init.setup import inject_paths
inject_paths()

# 2. Settings (pydantic is now importable)
from app.init.configs import SETTINGS

def bootstrap() -> None:
    """
    Execute all startup tasks.

    1. inject_paths() — already done at module level above
    2. DLL registration (Windows frozen only)
    3. Bundled ffmpeg on PATH (for third-party libs that shell out by name)
    4. Logging config

    NOTE: third-party compat patches are NOT applied here — importing the
    patched libs (torchvision, scipy) is ~4 s and must stay off the
    bind-blocking startup path. The torchvision functional_tensor shim is now
    applied lazily at its consumer chokepoint (PthWrapper._load_with_spandrel),
    and the scipy.signal.gaussian patch lives in its sole consumer
    (adapters/ai/wrapper/basic_pitch.py). See app/init/compat.py.
    """
    from app.init.setup import register_bundled_binaries, register_dlls
    register_dlls(SETTINGS)
    register_bundled_binaries(SETTINGS)

    from app.init.logging_config import configure_logging
    configure_logging(SETTINGS)
