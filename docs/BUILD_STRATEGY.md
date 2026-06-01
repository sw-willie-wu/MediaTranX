# MediaTranX Build & Distribution Strategy

> 打包架構、依賴管理與原始碼保護策略。

---

## 核心原則

| 目標 | 方案 |
|------|------|
| 原始碼保護 | Nuitka 編譯成 native binary（`core.exe`） |
| 依賴管理 | uv 管理 .venv，安裝在 `%APPDATA%/MediaTranX/` |
| AI 套件（torch 等）| 首次啟動後在 Settings 安裝 |
| 開發模式 | 不變，Electron 帶起 Vite + uvicorn |

---

## 目錄結構

### 安裝目錄（`%LOCALAPPDATA%/MediaTranX/`）

```
MediaTranX.exe                      ← Electron 主程式
resources/
  core_service/                     ← Nuitka 編譯的後端（standalone）
    core.exe                        ← FastAPI backend binary
    python312.dll
    *.dll                           ← 依賴的 native 模組
  uv.exe                            ← uv 執行檔（管理 .venv）
  pyproject.toml                    ← Python 依賴定義
  uv.lock                           ← 依賴鎖定檔
  ffmpeg/                           ← FFmpeg + FFprobe
  frontend_dist/                    ← Vite build 靜態檔
```

### 用戶資料（`%APPDATA%/MediaTranX/`）

```
.venv/                              ← uv 管理，首次安裝 AI 環境時建立
  Lib/site-packages/
    faster_whisper/
    torch/                          ← Step 2: PyTorch（CUDA / CPU）
    torchaudio/
    demucs/
    transformers/
    huggingface_hub/
    ...
models/                             ← AI 模型（按需下載）
  whisper/
  demucs/
  alignment/
  llm/
  vlm/
  upscale/
bin/llama/                          ← llama-server binary（Step 3 下載）
temp/                               ← 處理暫存
logs/                               ← 應用日誌
mediatranx.db                       ← SQLite（連線設定、任務歷史）
```

---

## 原始碼保護：Nuitka

### 編譯策略

```
我們的程式碼 → Nuitka 編譯 → core.exe（native binary）
AI 套件     → 排除（--nofollow-import-to）→ 運行時從 .venv import
```

### Nuitka 排除的套件（在 .venv 安裝）

```
torch, torchvision, torchaudio, transformers, PIL, numpy, scipy,
cv2, rembg, onnxruntime, ctranslate2, faster_whisper, demucs,
huggingface_hub, basicsr, realesrgan, facexlib, gfpgan, spandrel,
timm, einops, mobile_sam, simple_lama_inpainting, docx, pypdf,
fitz, pymupdf, lxml, tokenizers, hf_xet, av
```

### Nuitka 額外包含的 stdlib

```
--include-module=_ssl
--include-module=sqlite3
--include-module=pdb
--include-module=cProfile          ← torch._dynamo 需要
--include-package=unittest
--include-package=xml              ← torchvision.datasets 需要
```

### Nuitka 相容性修補

打包後 `__file__` 路徑可能指向 `core_service/` 而非 `.venv/site-packages/`。
集中修補在 `backend/app/init/nuitka_compat.py`：

| 修補 | 說明 |
|------|------|
| `_patch_torch_dynamo` | 假模組繞過 `transformers.masking_utils` |
| `_patch_demucs_remote_root` | 修正 demucs 的 `remote/files.txt` 路徑 |

---

## AI 環境安裝（3 步驟）

使用者在 Settings > AI 環境 點擊安裝：

| Step | 內容 | 方式 |
|------|------|------|
| 1/3 | 工具執行模組（Whisper、Demucs、HuggingFace 等） | `uv sync --extra ai`（永遠執行）+ Demucs GitHub install |
| 2/3 | PyTorch + torchvision + torchaudio | `uv pip install --index-url` 從 CUDA/CPU index |
| 3/3 | llama-server binary | 從 GitHub releases 下載 |

### DLL 注入（`init/dll_injection.py`）

`core.exe` 啟動時注入 `.venv/site-packages` 到 `sys.path`，
並用 `os.add_dll_directory()` 註冊 torch、ctranslate2 等的 DLL 路徑。

---

## Build Pipeline

### 腳本

```
scripts/
├── build.bat              ← 主 build（Vue + Nuitka + Electron）
├── build-test.bat         ← 測試 build（自動 bump dev 版號）
├── build_vue.bat          ← Step 1: npm run build
├── build_python.bat       ← Step 2: Nuitka 編譯
├── build_electron.bat     ← Step 3: electron-builder
└── release.bat            ← 正式發版（merge + bump + build + tag + push）
```

### 正式 Build 流程

```bash
scripts\build.bat
```

1. **Vue build** → `build/resources/frontend_dist/`
2. **Nuitka** → `build/resources/core_service/core.exe`
3. **Electron Builder** → `dist/MediaTranX-Setup-{version}-win.exe`

### 測試 Build 流程

```bash
scripts\build-test.bat
```

自動：讀版號 → bump minor → dev.N → build → 還原版號

```
package.json: 1.1.0
  → 1.2.0-dev.1 (自動遞增)
  → build
  → 還原回 1.1.0
  → dist/MediaTranX-Setup-1.2.0-dev.1-win.exe
```

---

## GPU Session 管理

`ModelManager.gpu_session()` 確保：
- 同時只有一個任務使用 GPU（`_gpu_lock`）
- 任務結束後**自動卸載所有模型**（含 llama-server subprocess）
- `gc.collect()` + `torch.cuda.empty_cache()` 清理 VRAM

---

## 安裝包大小

| 項目 | 大小 |
|------|------|
| Electron + frontend | ~100 MB |
| core.exe（Nuitka standalone） | ~125 MB |
| uv.exe | ~15 MB |
| FFmpeg + FFprobe | ~150 MB |
| **總計（installer）** | **~210 MB** |
| AI 環境（uv sync --extra ai） | ~1 GB |
| PyTorch CUDA（按需） | ~2.5 GB |
| AI 模型（按需） | 依模型而定 |
