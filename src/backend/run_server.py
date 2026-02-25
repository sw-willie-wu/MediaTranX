"""
PyInstaller 進入點
打包後由 backend.exe 直接執行此腳本
"""
import logging
import sys
from pathlib import Path

# frozen 模式下將 log 輸出到安裝目錄的 backend.log
if getattr(sys, 'frozen', False):
    log_path = Path(sys.executable).parent.parent.parent / 'backend.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(str(log_path), encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )
    logging.info(f"Backend log: {log_path}")

import uvicorn

from backend.main import app

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8001)
