"""
應用程式啟動 Bootstrap
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
按正確順序執行所有啟動前置作業。
必須在 import FastAPI 等第三方套件之前呼叫 bootstrap()。
"""
import logging


def bootstrap(is_frozen: bool) -> None:
    """
    執行所有啟動前置作業

    順序重要：
    1. DLL/路徑注入（讓後續 import 能找到套件和 DLL）
    2. 相容層（修補第三方套件的 API 變動）
    3. 日誌配置（後續所有模組的 logger 才能正常輸出）
    4. 啟動診斷（frozen 模式下檢查關鍵元件）
    """
    # 1. DLL 與 sys.path 注入
    from app.init.dll_injection import inject_paths
    inject_paths()

    # 2. 第三方套件相容層
    from app.init.compat import apply_compat_patches
    apply_compat_patches()

    # 3. 日誌配置
    from app.init.logging_config import configure_logging
    configure_logging(is_frozen)

    # 4. Nuitka 相容性修補（僅 frozen 模式）
    if is_frozen:
        from app.init.nuitka_compat import apply_nuitka_patches
        apply_nuitka_patches()

    # 5. 啟動診斷（僅 frozen 模式）
    if is_frozen:
        _run_diagnostics()


def _run_diagnostics() -> None:
    """Frozen 模式啟動診斷"""
    try:
        from app.engine.ai.model_manager import get_model_manager
        llama_ok = get_model_manager().is_llama_ready()
        logging.info(f"Startup Diagnostic: llama-server binary {'found' if llama_ok else 'NOT found'}")
    except Exception as e:
        logging.error(f"Startup Diagnostic: llama-server check failed: {e}")
