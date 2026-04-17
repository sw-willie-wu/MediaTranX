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
    3. Compat patches (third-party API fixes)
    4. Logging config
    """
    from app.init.setup import register_dlls
    register_dlls(SETTINGS)

    from app.init.compat import apply_compat_patches
    apply_compat_patches()

    from app.init.logging_config import configure_logging
    configure_logging(SETTINGS)
