"""
DLL 與 sys.path 注入
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
打包後的 exe 需要手動注入外部 .venv 的 site-packages 和 DLL 搜尋路徑。
必須在 import FastAPI 等任何第三方套件之前執行。
"""
import os
import sys
from pathlib import Path


def inject_paths() -> None:
    """注入 sys.path 和 DLL 搜尋路徑"""
    appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
    if not appdata:
        return

    # 注入外部 .venv site-packages（即使目錄尚不存在也先加入，安裝後即可 import）
    venv_site = os.path.join(appdata, 'MediaTranX', '.venv', 'Lib', 'site-packages')
    if venv_site not in sys.path:
        sys.path.append(venv_site)

    # DLL 搜尋路徑（需 os.add_dll_directory 支援，Windows 10+）
    if not hasattr(os, 'add_dll_directory'):
        return

    venv_base = os.path.join(appdata, 'MediaTranX', '.venv')
    dll_dirs = [
        os.path.join(venv_base, 'Scripts'),           # python312.dll 等
        os.path.join(venv_site, 'torch', 'lib'),      # torch CUDA DLL
        os.path.join(venv_site, 'ctranslate2'),        # ctranslate2 DLL（faster-whisper 底層）
        os.path.join(venv_site, 'tokenizers'),         # tokenizers .pyd 同層 DLL
    ]
    for d in dll_dirs:
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass

    # 動態掃描 site-packages 下所有 .libs 目錄（delvewheel 打包慣例）
    if os.path.isdir(venv_site):
        try:
            for entry in os.scandir(venv_site):
                if entry.is_dir() and entry.name.endswith('.libs'):
                    try:
                        os.add_dll_directory(entry.path)
                    except Exception:
                        pass
        except Exception:
            pass

    # 從 pyvenv.cfg 讀取 base Python 安裝目錄（含 vcruntime140.dll）
    pyvenv_cfg = os.path.join(venv_base, 'pyvenv.cfg')
    if os.path.isfile(pyvenv_cfg):
        try:
            with open(pyvenv_cfg, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.lower().startswith('home'):
                        py_home = line.split('=', 1)[1].strip()
                        if os.path.isdir(py_home):
                            try:
                                os.add_dll_directory(py_home)
                            except Exception:
                                pass
                        break
        except Exception:
            pass

    # CUDA DLL 路徑（%APPDATA%/MediaTranX/cuda/）
    if sys.platform == "win32":
        cuda_dir = os.path.join(appdata, 'MediaTranX', 'cuda')
        if os.path.isdir(cuda_dir):
            os.environ["PATH"] = cuda_dir + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(cuda_dir)
            except Exception:
                pass
