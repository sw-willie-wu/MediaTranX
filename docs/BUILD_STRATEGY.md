# MediaTranX Build & Distribution Strategy

> 本文件定義打包架構、依賴管理與原始碼保護策略。

---

## 核心原則

| 目標 | 方案 |
|------|------|
| 原始碼保護 | Nuitka 編譯成 native binary |
| 依賴管理 | uv 管理 venv，安裝在 AppData |
| 首次安裝免網路 | wheels 預打包進 installer |
| 進階 AI 套件（torch 等）| 按需下載，用戶觸發 |
| 開發模式 | 完全不變，仍用 .venv |

---

## 目錄結構

### 安裝目錄（`C:\Program Files\MediaTranX\`）

```
MediaTranX.exe                  ← Electron 主程式
resources/
  app/                          ← 前端 (Vite build) + Electron main.js
  backend.exe                   ← Nuitka 編譯的後端（native binary，原始碼已保護）
  uv.exe                        ← uv 執行檔（隨 app 打包，用於管理 venv）
  pyproject.toml                ← Python 依賴定義
  wheels/                       ← 預打包 wheels（首次安裝不需網路）
    fastapi-*.whl
    uvicorn-*.whl
    pillow-*.whl
    faster_whisper-*.whl
    llama_cpp_python-*.whl
    ...（所有基礎依賴）
  bin/                          ← Binary 工具
    ffmpeg/
    realesrgan/                 ← 空目錄，按需下載
    waifu2x/                    ← 空目錄，按需下載
```

### 用戶資料（`%APPDATA%\MediaTranX\`）

```
.venv/                          ← uv 管理，首次啟動建立，跨版本更新保留
  Scripts/
    python.exe
  Lib/site-packages/
    fastapi/
    pillow/
    faster_whisper/
    llama_cpp/
    torch/                      ← 可選，用戶在設定頁面安裝
    basicsr/                    ← 可選（SwinIR、HAT）
    codeformer/                 ← 可選（臉部修復）
cuda/                           ← CUDA DLL（按需下載）
models/                         ← AI 模型（按需下載）
  whisper/
  translate/
temp/                           ← 暫存檔案
```

---

## 原始碼保護：Nuitka

### 保護機制

Nuitka 將 Python 原始碼編譯為 C，再編譯成 native binary。

- 反編譯難度遠高於 PyInstaller（PyInstaller 可被 `pyinstxtractor` 輕鬆解包）
- 需要 IDA Pro 等專業工具才能分析
- **僅保護我們自己的後端原始碼**，不保護第三方套件（套件本身開源）

### 什麼被保護

```
backend/          ← 全部編譯進 backend.exe
  main.py
  api/
  core/
  services/
  workers/
```

### 什麼不被保護（也不需要）

```
wheels/           ← 開源套件，保護無意義
bin/              ← 第三方 binary
```

### 關鍵設計：保護程式碼 + 使用外部 venv

Nuitka 編譯時只包含我們的後端程式碼（不包含第三方套件），
`backend.exe` 啟動時動態注入 venv：

```python
# backend/main.py — 最頂部，Nuitka 編譯後仍會執行
import sys, os

_appdata = os.environ.get('APPDATA', '')
_venv_site = os.path.join(_appdata, 'MediaTranX', '.venv', 'Lib', 'site-packages')
if os.path.isdir(_venv_site):
    sys.path.insert(0, _venv_site)
    # torch DLL 需要額外處理
    _torch_lib = os.path.join(_venv_site, 'torch', 'lib')
    if os.path.isdir(_torch_lib) and hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(_torch_lib)
```

---

## 依賴管理：uv + pyproject.toml

### `pyproject.toml` 結構

```toml
[project]
name = "mediatranx-backend"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pillow>=11.0",
    "faster-whisper>=1.1",
    "llama-cpp-python>=0.3",
    "python-multipart",
    "aiofiles",
]

[project.optional-dependencies]
# 進階 AI 模型（按需安裝，需 ~2.5 GB CUDA torch）
ai = [
    "torch>=2.5",
    "torchvision>=0.20",
    "basicsr>=1.4",         # SwinIR, HAT
    "facexlib>=0.3",        # CodeFormer 依賴
    "codeformer-pytorch",   # 臉部修復
]

[tool.uv.sources]
# torch 走 PyTorch 官方 index，根據偵測到的驅動版本選擇
torch = [
    { index = "pytorch-cu124", marker = "platform_system == 'Windows'" },
]
torchvision = [
    { index = "pytorch-cu124", marker = "platform_system == 'Windows'" },
]

[[tool.uv.index]]
name = "pytorch-cu124"
url = "https://download.pytorch.org/whl/cu124"
explicit = true
```

> GPU 版本偵測邏輯在 `main.js`：根據 `nvidia-smi` 回傳的驅動版本，
> 動態修改 uv index URL（cu118 / cu121 / cu124 / cpu）。

### 依賴安裝時機

| 套件群組 | 安裝時機 | 指令 |
|---------|---------|------|
| 基礎依賴 | 首次啟動（從 wheels/ 離線安裝）| `uv sync --offline` |
| 新版本新增依賴 | app 更新後首次啟動 | `uv sync --offline`（自動補裝）|
| torch + AI 套件 | 用戶在設定頁面點擊安裝 | `uv sync --extra ai` |

---

## 啟動流程

### 首次啟動

```
Electron 啟動
  ↓
main.js 檢查 %APPDATA%/MediaTranX/.venv 是否存在
  ↓
不存在 → 顯示 "初始化環境..." 畫面（新的 splash 狀態）
         執行: uv sync --offline --find-links=resources/wheels/
         建立 .venv（從 wheels/ 離線安裝，約 30-60 秒）
         完成 → 繼續
  ↓
存在 → 執行 backend.exe（帶 APPDATA 環境變數）
  ↓
等待 port 8001 就緒（同現有邏輯）
  ↓
載入前端
```

### 之後每次啟動

```
Electron 啟動
  ↓
main.js 檢查 .venv 是否需要更新
（比對 resources/pyproject.toml hash 與上次安裝記錄）
  ↓
需要更新 → uv sync --offline（補裝新依賴，通常幾秒）
不需要 → 直接啟動
  ↓
啟動 backend.exe
```

### 進階 AI 套件安裝（用戶觸發）

```
設定頁面 → 安裝進階 AI 功能
  ↓
偵測 GPU 驅動版本（nvidia-smi）
  ↓
選擇對應 torch index：
  驅動 ≥ 560 → pytorch-cu124
  驅動 ≥ 527 → pytorch-cu121
  驅動 ≥ 452 → pytorch-cu118
  無 GPU    → pytorch-cpu
  ↓
uv sync --extra ai（下載 ~2.5 GB，顯示進度）
  ↓
完成 → 提示重啟 backend（重新載入 sys.path）
```

---

## Build Pipeline

```
build/
  build.bat           ← 主 build 腳本
  collect-wheels.bat  ← 收集依賴 wheels
  nuitka-build.bat    ← 編譯後端
```

### 執行順序

```bat
:: 1. 前端 build（不變）
cd src/frontend
npm run build

:: 2. 收集依賴 wheels（離線安裝用）
uv export --no-hashes -o requirements.txt
uv pip download -r requirements.txt -d resources/wheels/

:: 3. Nuitka 編譯後端
uv run nuitka \
  --standalone \
  --onefile \
  --output-filename=backend.exe \
  --output-dir=resources/ \
  --nofollow-import-to=torch \
  --nofollow-import-to=torchvision \
  --nofollow-import-to=fastapi \
  --nofollow-import-to=uvicorn \
  --nofollow-import-to=PIL \
  --nofollow-import-to=faster_whisper \
  --nofollow-import-to=llama_cpp \
  src/backend/backend/main.py

:: 4. 打包 uv.exe（從 GitHub releases 下載最新版）
:: 5. electron-builder 打包 installer
cd src/frontend
npm run build:installer
```

---

## 開發模式（完全不變）

```bash
cd src/frontend
npm run electron
```

- 仍使用 `.venv/Scripts/python.exe`
- 仍使用 uvicorn 直接啟動 `src/backend`
- 不需要 Nuitka，不需要 uv.exe

---

## 版本更新策略

| 情境 | 行為 |
|------|------|
| app 更新（新版 backend.exe）| 直接替換，.venv 保留 |
| 新增 Python 依賴 | 更新 pyproject.toml → 下次啟動 uv sync 自動補裝 |
| 用戶已安裝 torch | 更新後保留，不需重裝 |
| .venv 損壞 | 刪除 .venv → 下次啟動自動重建 |
| Python 版本升級 | 更新 requires-python → uv 自動處理 |

---

## 安裝包大小預估

| 項目 | 大小 |
|------|------|
| Electron | ~120 MB |
| backend.exe（Nuitka）| ~15 MB |
| uv.exe | ~15 MB |
| wheels/（基礎依賴）| ~80 MB |
| bin/ffmpeg | ~70 MB |
| **總計（installer）** | **~300 MB** |
| torch CUDA（按需）| ~2.5 GB |
| AI 模型（按需）| 依模型而定 |
