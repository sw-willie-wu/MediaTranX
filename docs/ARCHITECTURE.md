# MediaTranX 專案架構文件 (Architecture)

> **專案定位**：基於 AI 的現代化多媒體處理平台，整合語音辨識、翻譯、圖片超解析與轉檔功能。
> **核心技術**：FastAPI (Backend) + Vue 3 (Frontend) + Electron (Desktop Wrapper) + Sidecar AI Runtime.

---

## 1. 系統整體架構 (System Overview)

MediaTranX 採用 **Client-Server** 架構，即使在案頭模式下也保持前後端分離：

- **Frontend (UI Layer)**: Vue 3 + TypeScript + Pinia，運行於 Electron 渲染進程。
- **Backend (Service Layer)**: FastAPI (Python 3.12)，提供 RESTful API 與 SSE (Server-Sent Events) 進度推送。
- **Sidecar (AI Layer)**: 透過 `uv` 管理的獨立 `.venv` 環境，包含大尺寸的 AI 推理依賴（如 PyTorch, llama-cpp-python）。

---

## 2. 後端架構 (Backend Architecture)

後端嚴格遵循 **三層架構 (3-Tier Architecture)**：

### 2.1 分層設計
1.  **API 路由層 (`api/routes/`)**：
    - 負責接收 HTTP 請求、參數驗證（Pydantic）。
    - 呼叫 Service 層，不直接接觸底層邏輯。
2.  **Service 業務層 (`services/`)**：
    - 實作單例模式 (Singleton)。
    - 協調多個 Core 組件，處理任務提交 (Task Submission)。
3.  **Core 底層封裝 (`core/`)**：
    - **Device**: 硬體自動偵測（CUDA/DirectML/CPU）。
    - **Paths**: 統一的路徑管理（相容開發與打包環境）。
    - **AI**: 封裝 AI 模型推理（Whisper, LLM, Upscale）。

### 2.2 核心組件
- **TaskManager**: 管理背景任務，使用 `ThreadPoolExecutor` 執行耗時操作，防止阻塞 API。
- **ModelManager**: 顯存 (VRAM) 調度中心，使用「模型槽 (Slot)」機制防止 OOM，確保影像與語言任務互斥。
- **ProgressTracker**: 基於 SSE 的進度追蹤器，將任務進度即時推送至前端。

---

## 3. 前端架構 (Frontend Architecture)

### 3.1 狀態管理 (Pinia)
- **TaskStore**: 維護任務列表、狀態（Pending/Processing/Completed）以及 SSE 連線管理。
- **FileStore**: 管理上傳檔案與 Electron 本地檔案註冊。
- **SettingsStore**: 儲存使用者偏好（主題、語言、路徑設定）。

### 3.2 UI 組件設計
- **ToolLayout**: 統一的工具頁面框架，提供預覽、參數設定與結果比對 (Slider) 功能。
- **Composables**: 
    - `useApi`: 封裝 Fetch 請求。
    - `useProgress`: 封裝 SSE 進度追蹤邏輯。
    - `useTheme`: 全域深色/淺色主題管理。

---

## 4. AI 整合機制 (AI Integration)

專案採用 **Sidecar 環境模式** 以優化安裝包大小：

- **核心包**: 僅包含 FastAPI 與基本工具。
- **AI 插件**: 首次啟動或需要 AI 功能時，透過 `uv` 動態安裝依賴至 `%APPDATA%/MediaTranX/.venv`。
- **模型管理**: 模型權重（如 Whisper weights, GGUF models）存放於 `%APPDATA%/MediaTranX/models/`，支援斷點續傳下載。

---

## 5. 數據路徑規範 (Data & Paths)

所有路徑透過 `core/paths.py` 管理，優先級如下：
1.  **MEDIATRANX_HOME** 環境變數。
2.  `config.json` 中的自定義路徑。
3.  預設值：`%APPDATA%/MediaTranX/`。

| 目錄類型 | 預設路徑 (Windows) | 說明 |
| :--- | :--- | :--- |
| **Models** | `.../MediaTranX/models/` | AI 模型權重儲存區 |
| **Venv** | `.../MediaTranX/.venv/` | AI 推理環境 (Sidecar) |
| **Temp** | `.../MediaTranX/temp/` | 處理過程中的暫存檔 |
| **Output** | `AppRoot/output/` | 最終產出檔案 |

---

## 6. 任務生命週期 (Task Lifecycle)

1.  **Submit**: 前端發送 `POST /api/domain/action`。
2.  **Register**: `TaskManager` 建立任務 ID，前端將其加入 `TaskStore`。
3.  **Subscribe**: 前端建立 `EventSource` 連接到 `/api/tasks/{id}/progress`。
4.  **Execute**: 後端 `Service` 呼叫 `ModelManager` 獲取顯存，開始 AI 推理。
5.  **Progress**: 推理過程中不斷透過 SSE 發送 `progress` 與 `message`。
6.  **Complete**: 任務結束，發送 `stage: "completed"` 並附帶 `result` (如 `output_file_id`)。
7.  **Display**: 前端收到完成信號，更換預覽介面為結果檔案。

---

## 7. 打包與部署 (Build & Packaging)

- **Backend**: 使用 PyInstaller 或 Nuitka 將 FastAPI 封裝為 `core.exe`。
- **Frontend**: Vite 建置靜態檔，Electron Forge 打包為安裝程式。
- **Third-party Binaries**: FFmpeg 等工具放置於 `bin/` 目錄，打包時移動至 `resources/`。
