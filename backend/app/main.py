"""
FastAPI 應用程式進入點
"""
import os
import sys

# --- 0. 偵測編譯模式 ---
IS_FROZEN = getattr(sys, 'frozen', False) or "__compiled__" in globals() or hasattr(sys, "nuitka_binary")

# --- 1. 修正編譯後的導入路徑（必須在任何 app.* import 之前）---
if IS_FROZEN:
    _internal_path = os.path.dirname(sys.executable)
    if _internal_path not in sys.path:
        sys.path.insert(0, _internal_path)

# --- 2. Bootstrap（DLL 注入、相容層、日誌）---
from app.init import bootstrap
bootstrap(IS_FROZEN)

# --- 3. App ---
from fastapi import FastAPI
from app.api import build_router

app: FastAPI = FastAPI(title="MediaTranX API")
app = build_router(app)

# --- 4. 服務啟動 ---
if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="MediaTranX Backend")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--mode", type=str, default="production", choices=["production", "dev"])
    args = parser.parse_args()

    is_dev = args.mode == "dev"
    if is_dev:
        os.environ["MEDIATRANX_DEV"] = "1"

    # 根據 mode 調整 app + uvicorn log level
    import logging as _logging
    app_level = _logging.DEBUG if is_dev else _logging.WARNING
    _logging.getLogger().setLevel(app_level)

    uvicorn.run(
        app, host=args.host, port=args.port,
        log_level="debug" if is_dev else "warning",
    )
