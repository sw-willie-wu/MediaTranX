# MediaTranX 專案架構文件 (Architecture)

> **專案定位**：基於 AI 的本地多媒體處理平台，整合語音辨識、翻譯、圖片超解析、OCR 與格式轉換功能。所有 AI 推理均在本機執行。
> **核心技術**：FastAPI (Backend) + Vue 3 (Frontend) + Electron (Desktop Wrapper) + llama-server / PyTorch (AI Runtime)

---

## 1. 系統整體架構

MediaTranX 採用 **Client-Server** 架構，前後端分離：

- **Frontend (UI Layer)**: Vue 3 + TypeScript + Pinia，運行於 Electron 渲染進程（開發時為 Vite dev server port 8000）
- **Backend (Service Layer)**: FastAPI (Python 3.12)，提供 RESTful API 與 SSE 進度推送（port 8001）
- **AI Runtime**: 兩種推理後端並存
  - `llama-server` subprocess（LLM 翻譯、VLM OCR）
  - PyTorch / Spandrel（圖片超解析、人臉修復）
  - CTranslate2（Whisper 語音辨識）

---

## 2. 後端架構

後端嚴格遵循 **三層架構**：

### 2.1 分層設計

1. **API 路由層 (`api/routes/`)**：接收 HTTP 請求、Pydantic 參數驗證，呼叫 Service 層
2. **Service 業務層 (`services/`)**：協調多個 Core 組件，處理任務提交
3. **Core 底層封裝 (`core/`)**：
   - **Device**: 硬體自動偵測（CUDA / CPU）
   - **Paths**: 統一路徑管理（相容開發與打包環境）
   - **AI**: 封裝 AI 模型推理

### 2.2 AI 模型系統（三層架構）

**Registry (`core/ai/registry.py`)**：格式優先樹狀結構，Single Source of Truth

```
MODELS_REGISTRY[FORMAT][model_id] → { slot, description, variants/specs }
```

| FORMAT | 說明 |
|---|---|
| `FORMAT_BIN` | CTranslate2 目錄型（Whisper） |
| `FORMAT_GGUF` | llama-server GGUF 文字 LLM |
| `FORMAT_PTH` | PyTorch 權重（超解析、人臉修復） |
| `FORMAT_VLM` | VLM（llama-server，雙檔：主模型 + mmproj） |

**Runtime 基礎層 (`core/ai/base/`)**：

| Runtime | 說明 |
|---|---|
| `BINRuntime` | CTranslate2，含 `_zombie_models` 防崩潰機制 |
| `PTHRuntime` | PyTorch/Spandrel，CUDA/CPU 自動切換 |
| `LlamaServerRuntime` | 啟動 llama-server subprocess，提供 OpenAI 相容 API |

**ModelManager**：VRAM 調度中心，使用「模型槽 (Slot)」機制防止 OOM

### 2.3 核心組件

- **TaskManager**: `ThreadPoolExecutor` 管理背景任務，防止阻塞 API
- **ProgressTracker**: SSE 進度推送至前端

---

## 3. 前端架構

### 3.1 View 結構

| View | 路由 | 說明 |
|---|---|---|
| `ImageView` | `/image` | 圖片工具（轉檔、去背、物件移除、超解析、濾鏡、裁切、壓縮、文字辨識） |
| `VideoView` | `/video` | 影片工具（轉檔、剪輯、字幕） |
| `AudioView` | `/audio` | 音訊工具（轉檔、剪輯、音量調整、逐字稿） |
| `DocumentView` | `/document` | 文件工具（翻譯、PDF 轉換、文字辨識、分割） |
| `SettingsView` | `/settings` | 設定（一般、模型管理、系統資訊、關於） |
| `SetupView` | `/setup` | AI 核心安裝精靈 |

### 3.2 Workspace Composables

每個 View 對應一個 workspace composable 管理檔案上傳、任務狀態與結果：

| Composable | 對應 View |
|---|---|
| `useImageWorkspace` | ImageView |
| `useVideoWorkspace` | VideoView |
| `useAudioWorkspace` | AudioView |
| `useDocumentWorkspace` | DocumentView |

### 3.3 Pinia Stores

- **TaskStore**: 任務列表、SSE 連線管理
- **FileStore**: 上傳檔案與 Electron 本地檔案註冊
- **SettingsStore**: 使用者偏好（主題、語言、路徑、裝置資訊）

### 3.4 ToolLayout 共用框架

所有工具 View 使用 `ToolLayout.vue` 統一框架：

- 左側：Preview 區域（圖片/影片/音訊播放器）
- 右側：Sub-function tab 列 + 設定 panel
- 底部工具列：執行按鈕、下載按鈕、媒體資訊 bar

**Preview 原則**：
- 圖片工具、影片剪輯/字幕 → 需要 preview（視覺確認或互動操作）
- 影片轉檔、音訊工具、文件工具 → 不需要 preview（純參數設定）

### 3.5 共用樣式

| 檔案 | 用途 |
|---|---|
| `styles/tool-panels-shared.scss` | Tool panels 共用樣式（非 scoped，全域注入） |
| `styles/settings-shared.scss` | Settings tab 元件共用樣式 |

---

## 4. 資料路徑規範

所有路徑透過 `core/paths.py` 管理，優先級：

1. `MEDIATRANX_HOME` 環境變數
2. `config.json` 中的自定義路徑
3. 預設值：`%APPDATA%/MediaTranX/`

| 目錄 | 預設路徑 (Windows) | 說明 |
|---|---|---|
| Models | `.../MediaTranX/models/` | AI 模型權重 |
| Venv | `.../MediaTranX/.venv/` | AI 推理環境 |
| Temp | `.../MediaTranX/temp/` | 處理暫存檔 |
| llama-bin | `bin/llama/`（dev）/ `resources/llama-bin/`（packaged） | llama-server binary |

---

## 5. 任務生命週期

1. **Submit**: 前端 `POST /api/domain/action`
2. **Register**: `TaskManager` 建立任務 ID，前端加入 `TaskStore`
3. **Subscribe**: 前端建立 `EventSource` 連到 `/api/tasks/{id}/progress`
4. **Execute**: 後端 Service 呼叫 `ModelManager` 取得 VRAM，開始推理
5. **Progress**: AI 推理過程中持續 SSE 發送 `progress` 與 `message`
6. **Complete**: 發送 `stage: "completed"` 附帶 `result`（如 `output_file_id`）
7. **Display**: 前端收到完成信號，更新 preview 或觸發下載

---

## 6. 打包與部署

- **Backend**: PyInstaller 封裝 FastAPI 為 `core.exe`
- **Frontend**: Vite 建置靜態檔，Electron Builder 打包
- **Third-party Binaries**: FFmpeg（`bin/ffmpeg/`）、llama-server（`bin/llama/`），打包時移至 `resources/`
- **生產環境**：Electron 用 `loadFile()` 載入本地 HTML（`file://` 協議），CORS 需包含 `"null"` origin
