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

### Nuitka 排除的第三方套件（在 .venv 安裝）

排除清單**不是手寫固定表**，而是 `scripts/build.py` `step_nuitka()` 於 backend venv 動態列舉：
`importlib.metadata.packages_distributions()` 取得所有已安裝套件，扣掉 `app` 與 `_` 開頭者，全部轉成 `--nofollow-import-to`（torch、transformers、cv2、ctranslate2、faster_whisper、demucs、rembg…等皆由此自動排除，隨 venv 實際安裝內容變動）。

### Nuitka 包含的模組

```
# pkg_includes（固定，--include-package）：
ctypes, importlib, email, http, xml, unittest, multiprocessing,
concurrent, urllib, logging, asyncio, json, html, collections, encodings,
app.services, app.adapters          ← 由 container._lazy() 動態 import，Nuitka 無法靜態發現，必須顯式補包

# 其餘 stdlib（動態，--include-module）：
sys.stdlib_module_names - _STDLIB_SKIP（逐個 __import__ 過濾），
_ssl / sqlite3 等 extension 會自動被掃進來，不需手動逐個指定
```

Nuitka 以 `nuitka==4.0.8` **pin**（避免版本漂移連帶要求更新的 MinGW 工具鏈）、`--standalone`、`--output-filename=core.exe`、`--assume-yes-for-downloads`（CI/背景 build 自動接受 MinGW64 下載）。

### 第三方套件相容性修補

相容性修補**延後 (lazy) 套用、不在 `bootstrap()`**——因為 import torchvision/scipy（~4s）必須移出 bind 阻塞啟動路徑（見 cold-start 優化）。

| 修補 | 位置 | 說明 |
|------|------|------|
| torchvision `functional_tensor` shim | `backend/app/init/compat.py` `ensure_torchvision_functional_tensor_compat()`，**在 `PthWrapper._load_with_spandrel` 載入模型前 lazy 套用**（idempotent） | 補回 basicsr 仍引用、新版 torchvision 已移除的 `transforms.functional_tensor`；現行無 app 路徑引用 basicsr，純防禦性保留 |
| scipy `signal.gaussian` shim | `backend/app/adapters/ai/wrapper/basic_pitch.py`（唯一消費者，於使用點 self-patch；舊 `compat.py` 版本已移除） | 補回新版 scipy 移到 `signal.windows` 的 `signal.gaussian` |

---

## AI 環境安裝（3 步驟）

由 **Electron 殼層管理**（`electron/setup.js`：GPU 偵測 → uv sync → binary 下載）：

| Step | 內容 | 方式 |
|------|------|------|
| 1/3 | 工具執行模組（Whisper、Demucs、HuggingFace 等） | `uv sync --extra ai`（永遠執行）+ Demucs GitHub install |
| 2/3 | PyTorch + torchvision + torchaudio | `uv pip install --index-url` 從 CUDA/CPU index |
| 3/3 | llama-server binary | 從 GitHub releases 下載 |

### DLL 注入（`init/setup.py`）

`core.exe` 啟動時（僅 `settings.is_frozen`）注入 `.venv/site-packages` 到 `sys.path`，
並用 `os.add_dll_directory()` 註冊 torch、ctranslate2、tokenizers、llama_cpp/lib、vcruntime（讀 pyvenv.cfg `home`）等 DLL 路徑。詳細踩坑見記憶檔 `nuitka-packaging-pitfalls.md`。

---

## Build Pipeline

### 腳本

2026-04 起以兩支 Python 腳本取代舊的 8 個 `.bat`（monorepo 後皆在頂層 `scripts/`）：

```
scripts/
├── build.py     ← build（vite + Nuitka + electron-builder）；--mode dev|prod、--step、--full
└── release.py   ← 正式發版（單 repo 6 步：merge + bump + build + tag + push + sync）
```

> **務必加 `uv run --project backend` 前綴**跑 build.py —— `step_nuitka()` 的排除清單是由「執行所在 venv 已安裝套件」算出，不在 backend venv 跑會壞。

### 正式 Build 流程

```bash
uv run --project backend python scripts/build.py --mode prod
```

三個 step（可用 `--step vite,nuitka,electron` 單獨跑）：

1. **vite** → `build/resources/frontend_dist/`（`npx vite build`）
2. **nuitka** → `build/resources/core_service/core.exe`
3. **electron** → `dist/MediaTranX-Setup-{version}-win.exe`（`--full` 才連 `.venv` + bin tools 一起打包）

### 測試 Build 流程

```bash
uv run --project backend python scripts/build.py --mode dev
```

dev 模式：版號 = 當前 base（依 `--bump`，default `minor`；亦可 `--version` 直接指定）→ 加 `-dev.N` 後綴（N 由掃 `dist/` 既有 `MediaTranX-Setup-{base}-dev.N-win.exe` 取最大 +1）→ build → **build 後自動還原版號**（dev build 不寫 `uv lock`）。

```
backend/pyproject.toml: 1.5.0
  → 1.5.1-dev.1（base 1.5.1 + 掃 dist/ 得 N）
  → build
  → 還原回 1.5.0
  → dist/MediaTranX-Setup-1.5.1-dev.1-win.exe
```

> 發版流程（release.py 6 步）細節見 [RELEASE.md](RELEASE.md)。

---

## GPU Session 管理

`ModelManager.gpu_session()` 確保：
- 同時只有一個任務使用 GPU（`_gpu_lock`）
- 任務結束後**自動卸載所有模型**（含 llama-server subprocess）
- `gc.collect()` + `torch.cuda.empty_cache()` 清理 VRAM

---

## 安裝包大小

預設 installer **不含** FFmpeg / `.venv` / bin tools（首次啟動由 Electron 下載）；只有 `--full` build 會把它們一起打包。

| 項目 | 大小 |
|------|------|
| Electron + frontend | ~100 MB |
| core.exe（Nuitka standalone） | ~125 MB |
| uv.exe | ~15 MB |
| **預設 installer（不含 AI 環境/FFmpeg）** | **~111–116 MB**（v1.5.0 ≈ 111 MB、v1.4.1 ≈ 116 MB） |
| 首次啟動下載：FFmpeg + FFprobe | ~150 MB |
| 首次啟動下載：AI 環境（uv sync --extra ai） | ~1 GB |
| 按需：PyTorch CUDA | ~2.5 GB |
| 按需：AI 模型 | 依模型而定 |
