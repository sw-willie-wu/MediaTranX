# -*- mode: python ; coding: utf-8 -*-
"""
MediaTranX 後端 PyInstaller 規格檔
使用方式: pyinstaller build/backend.spec
"""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs, collect_data_files

PROJECT_ROOT = Path(SPECPATH).parent
SRC_DIR = PROJECT_ROOT / 'src'
BACKEND_DIR = SRC_DIR / 'backend'
STATIC_DIR = BACKEND_DIR / 'static'

# 收集所有 backend 子模組
backend_imports = collect_submodules('backend')

# 收集 llama_cpp 動態庫（含 GGML 後端）
llama_binaries = collect_dynamic_libs('llama_cpp')

# 收集 ctranslate2 動態庫
ct2_binaries = collect_dynamic_libs('ctranslate2')

# 收集 CUDA 動態庫（from nvidia pip packages）
# nvidia Python 模組仍排除（不需要），但 DLLs 必須打包
# 放到根目錄 '.' 讓 ctypes.CDLL() 和動態連結都能找到
VENV_SITE = PROJECT_ROOT / '.venv' / 'Lib' / 'site-packages'
cuda_dll_dirs = [
    VENV_SITE / 'nvidia' / 'cublas' / 'bin',
    VENV_SITE / 'nvidia' / 'cuda_runtime' / 'bin',
    VENV_SITE / 'nvidia' / 'cudnn' / 'bin',
]
cuda_binaries = []
for dll_dir in cuda_dll_dirs:
    if dll_dir.exists():
        for dll in dll_dir.glob('*.dll'):
            cuda_binaries.append((str(dll), '.'))

# 收集 faster_whisper 的資料檔（含 silero_vad ONNX 模型）
faster_whisper_datas = collect_data_files('faster_whisper')

# 額外需要明確列出的 hidden imports
extra_imports = [
    # uvicorn 子模組
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    # FastAPI / Starlette
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    'starlette.middleware.gzip',
    'starlette.responses',
    'starlette.staticfiles',
    # Pydantic
    'pydantic',
    'pydantic_settings',
    'pydantic.deprecated.decorator',
    # HTTP
    'httptools',
    'httptools.parser',
    'httptools.parser.parser',
    # Async
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    # 其他 backend 依賴
    'aiofiles',
    'multipart',
    'python_multipart',
    # AI / ML
    'llama_cpp',
    'faster_whisper',
    'ctranslate2',
    'huggingface_hub',
    'sentencepiece',
    'PIL',
    'PIL.Image',
    # Windows
    'win32api',
    'win32con',
    'pywintypes',
]

# 排除 CUDA/GPU 相關套件（由使用者環境提供）
excludes = [
    'torch',
    'torchvision',
    'torchaudio',
    'nvidia',
    'nvidia.cublas',
    'nvidia.cuda_runtime',
    'nvidia.cudnn',
    'nvidia.cufft',
    'nvidia.curand',
    'nvidia.cusolver',
    'nvidia.cusparse',
    'nvidia.nccl',
    'nvidia.nvjitlink',
    'nvidia.nvtx',
    # 大型不需要的套件
    'matplotlib',
    'scipy',
    'pandas',
    'numpy.testing',
    'IPython',
    'jupyter',
    'notebook',
    'pytest',
    'tkinter',
]

a = Analysis(
    [str(SRC_DIR / 'backend' / 'run_server.py')],
    pathex=[str(SRC_DIR)],
    binaries=llama_binaries + ct2_binaries + cuda_binaries,
    datas=[
        # Vite build 產物 → static/
        (str(STATIC_DIR), 'static'),
    ] + faster_whisper_datas,
    hiddenimports=backend_imports + extra_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# 移除 PyInstaller DLL 掃描自動拉進來的 torch/ 和 nvidia/ 子目錄副本
# 這些是 CUDA DLLs 的重複（已在根目錄有一份 from cuda_binaries）
# torch/lib/ ~750MB, nvidia/ ~840MB 全是重複，不移除會超過 NSIS 2GB 限制
a.binaries = [b for b in a.binaries
              if not b[0].startswith(('torch\\', 'torch/', 'nvidia\\', 'nvidia/'))]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 顯示 console 方便除錯
    icon=str(PROJECT_ROOT / 'src' / 'frontend' / 'src' / 'assets' / 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='backend',
)
