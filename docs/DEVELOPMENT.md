# MediaTranX 開發文件

> 此文件為專案開發規範，所有後續開發均須遵循。

---

## 目錄結構

```
MediaTranX/
├── bin/                        # 第三方二進位工具（不進 git）
│   └── ffmpeg/                 # FFmpeg 執行檔
├── src/
│   ├── backend/                # Python FastAPI 後端
│   ├── frontend/               # Vue 3 前端（純 Vite，無 Electron）
│   └── electron/               # Electron 主進程（main.js, preload.cjs, splash.html）
├── docs/                       # 文件
└── .venv/                      # Python 虛擬環境（uv 管理）
```

> AI 模型與 `.venv` 存放於 `%APPDATA%/MediaTranX/`，不在專案目錄內。

---

## 後端架構

### 分層結構

後端嚴格遵循三層架構，由上至下依序為：

```
API 路由層 (api/routes/)
    └─ 接收 HTTP 請求，驗證參數，呼叫 Service
Service 層 (services/)
    └─ 業務邏輯、任務提交、協調 Core
Core 層 (core/)
    └─ 與外部工具/AI 模型互動的底層封裝
```

**規則：路由只呼叫 Service，Service 呼叫 Core，不可跨層跳躍。**

### 目錄結構

```
src/backend/
├── main.py                     # FastAPI app 建立，掛載 build_router()
├── run_server.py               # 打包後的進入點（uvicorn 啟動）
├── api/
│   ├── __init__.py             # build_router(app) → 掛載 /api 路由
│   ├── middleware.py           # CORS 等中間件
│   ├── routes/
│   │   ├── __init__.py         # 彙總所有子路由
│   │   ├── health.py           # GET /api/health, /api/device
│   │   ├── files.py            # GET/POST /api/files/...
│   │   ├── tasks.py            # GET/POST/DELETE /api/tasks/... + SSE
│   │   ├── setup.py            # GET /api/setup/... (首次設定)
│   │   ├── video/
│   │   │   ├── transcode.py    # POST /api/video/transcode
│   │   │   └── subtitle.py     # POST /api/video/subtitle/...
│   │   ├── audio/
│   │   │   └── transcode.py    # POST /api/audio/transcode
│   │   ├── image/
│   │   │   ├── convert.py      # GET /api/image/info/{id}, POST /api/image/convert
│   │   │   └── upscale.py      # GET /api/image/upscale/status, POST /api/image/upscale
│   │   └── document/
│   │       └── translate.py    # POST /api/document/translate
│   └── schemas/
│       └── common.py           # 共用 Pydantic schema（FileInfo, TaskResponse 等）
├── core/
│   ├── device.py               # GPU/CPU 自動偵測
│   ├── ffmpeg.py               # FFmpeg 封裝（影音處理）
│   ├── paths.py                # 路徑管理（dev/packaged 雙模式）
│   └── ai/                     # AI 模型封裝
│       ├── model_manager.py    # VRAM 管理（LRU 驅逐）
│       ├── base_translator.py  # 翻譯基礎類別
│       ├── whisper.py          # faster-whisper STT
│       ├── translategemma.py   # TranslateGemma (Gemma 2)
│       ├── qwen3.py            # Qwen3 翻譯
│       └── translation.py      # get_translator() 分發器
├── workers/
│   ├── task_manager.py         # ThreadPoolExecutor 任務佇列
│   └── progress_tracker.py     # SSE 進度推送（ProgressEvent）
└── services/
    ├── __init__.py             # 匯出所有 Service 和 get_xxx() 函數
    ├── files/
    │   └── file_service.py     # 檔案管理（上傳、下載、本地註冊）
    ├── video/
    │   ├── transcode_service.py
    │   └── subtitle_service.py
    ├── audio/
    │   └── transcode_service.py
    ├── image/
    │   ├── convert_service.py  # PIL 圖片格式轉換
    │   └── upscale_service.py  # Real-ESRGAN / waifu2x 超解析
    └── document/
        └── translate_service.py
```

### paths.py — 路徑管理規範

所有外部工具/資源路徑**必須**透過 `core/paths.py` 取得，不可在其他地方 hardcode 路徑。

```python
# 每個路徑函數都處理 dev（bin/） 和 packaged（PyInstaller frozen）兩種模式
from backend.core.paths import get_ffmpeg_dir, get_realesrgan_dir, get_waifu2x_dir

exe = get_realesrgan_dir() / "realesrgan-ncnn-vulkan.exe"
```

新增二進位工具時，在 `paths.py` 加對應的 `get_xxx_dir()` 函數。

### Service 單例模式

所有 Service 使用 `__new__` 單例 + `_initialized` 守門：

```python
class MyService:
    _instance: Optional["MyService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        # ... 初始化 ...
        self._initialized = True

def get_my_service() -> MyService:
    global _my_service
    if _my_service is None:
        _my_service = MyService()
    return _my_service
```

`services/__init__.py` 統一匯出所有 Service 類別和 `get_xxx()` 函數。

### 任務系統（Task System）

所有耗時操作（轉檔、AI 推論等）均透過任務系統非同步執行：

```
前端 POST /api/xxx → 路由呼叫 service.submit_xxx() → TaskManager.submit()
                                                            ↓
                                              ThreadPoolExecutor 執行 _handle_xxx_task()
                                                            ↓
                                              progress_callback() → ProgressTracker.emit()
                                                            ↓
                                              SSE: GET /api/tasks/{id}/progress
                                                            ↓
                                              前端收到 progress >= 1.0，讀取 data.result
```

**ProgressEvent 欄位：**
- `progress`: 0.0 ~ 1.0
- `stage`: `"processing"` / `"completed"` / `"error"` / `"heartbeat"`
- `message`: 使用者可讀的階段描述
- `result`: 僅在 `progress >= 1.0` 時存在，包含輸出結果（如 `output_file_id`）

**規則：最終 emit 必須帶 `result`，前端才能知道輸出在哪。**

```python
# task_manager.py 完成時：
await self._progress_tracker.emit(
    task_id, 1.0, "Task completed",
    stage="completed",
    result=result if isinstance(result, dict) else None,
)
```

### API 路由撰寫規範

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class MyRequest(BaseModel):
    file_id: str
    option: str = "default"

@router.post("/my-endpoint")
async def my_endpoint(request: MyRequest):
    service = get_my_service()
    try:
        task_id = await service.submit_xxx(
            file_id=request.file_id,
            option=request.option,
        )
        return {"task_id": task_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 前端架構

### 技術棧

- Vue 3 Composition API + `<script setup>`
- TypeScript
- Pinia（狀態管理）
- Vue Router
- SCSS（scoped，每個元件自帶樣式）

### 目錄結構

```
src/frontend/src/
├── main.ts                     # 應用入口，掛載 Pinia + Router
├── App.vue                     # 根元件（Titlebar + RouterView + MainSidebar + AppToast）
├── router/
│   └── index.ts                # 路由定義
├── stores/
│   ├── tasks.ts                # 任務狀態（Map<taskId, Task> + SSE 管理）
│   ├── files.ts                # 檔案狀態（uploadFile, registerLocalFile）
│   └── settings.ts             # 設定（主題、語言等）
├── composables/
│   ├── useApi.ts               # API fetch 封裝
│   ├── useToast.ts             # Toast 通知
│   ├── useTheme.ts             # 主題管理
│   └── useProgress.ts          # SSE 進度追蹤
├── components/
│   ├── ToolLayout.vue          # 工具頁面框架（三欄式 + 預覽 + slider 比對）
│   ├── AppToast.vue            # 全域 Toast
│   ├── MainSidebar.vue         # 左側任務列
│   ├── Titlebar.vue            # 自訂標題列
│   ├── common/                 # 可復用 UI 元件
│   │   ├── AppMediaInfoBar.vue # 媒體資訊欄（解析度、格式、大小等）
│   │   ├── AppUploadZone.vue   # 拖曳上傳區
│   │   ├── AppSelect.vue       # 下拉選單
│   │   ├── AppRange.vue        # 滑桿
│   │   ├── ProgressBar.vue     # 進度條
│   │   └── TaskQueue.vue       # 任務列表
│   └── video/
│       └── SubtitlePanel.vue   # 字幕面板（僅 VideoView 使用）
├── views/
│   ├── HomeView.vue
│   ├── VideoView.vue           # 參考實作（最完整）
│   ├── ImageView.vue
│   ├── AudioView.vue
│   ├── DocumentView.vue
│   ├── SettingsView.vue
│   ├── TasksView.vue
│   └── HistoryView.vue
└── types/
    ├── task.ts                 # Task, ProgressUpdate
    ├── media.ts                # 媒體類型
    └── api.ts                  # API 回應類型
```

### ToolLayout.vue — 工具頁面框架

所有工具頁面透過 `<ToolLayout>` 組合，不自己實作三欄佈局。

**Props：**
| Prop | 類型 | 說明 |
|------|------|------|
| `tools` | `Tool[]` | 左欄子功能列表 |
| `previewUrl` | `string?` | 原圖預覽（blob URL 或路徑） |
| `resultPreviewUrl` | `string?` | 結果預覽（後端下載 URL） |
| `hidePreviewTabs` | `boolean` | 隱藏 tab（影片工具用） |
| `activeTool` | `string` | 目前選中的子功能 ID |

**Slots：**
- `settings`：右欄設定面板內容
- 預覽區由 ToolLayout 自行管理（含 slider 比對）

**Events：**
- `@file-dropped(file, srcDir)`：檔案拖曳
- `@remove-file`：移除檔案按鈕點擊

**slider 比對模式：**
- 有 `resultPreviewUrl` 時，右上角出現比對按鈕
- 點擊進入 slider 模式：左半原圖、右半結果，中間拖曳分隔線
- 使用 `clip-path: inset(0 0 0 X%)` 裁切結果圖
- 圖片 CSS 必須用 `width: 100%; height: 100%; object-fit: contain`（不可用 max-width/max-height，否則 clip-path % 會錯位）

### Pinia Stores 使用規範

**tasks store（`Map` 結構）：**
```typescript
const taskStore = useTaskStore()

// 正確：Map 用 .get()，不用 .find()
const task = taskStore.tasks.get(taskId)

// 新增任務後自動訂閱 SSE
taskStore.addTask({
  taskId,
  taskType: 'image.convert',
  status: 'pending',
  progress: 0,
  message: '',
  result: null,
  error: null,
  label: '圖片轉檔',
  fileName: file.name,
  createdAt: new Date(),
  updatedAt: new Date(),
})
```

**files store：**
```typescript
const filesStore = useFilesStore()

// 上傳（Web 環境）
const fileInfo = await filesStore.uploadFile(file, sourceDir)

// 本地註冊（Electron，不複製檔案）
const fileInfo = await filesStore.registerLocalFile(filePath)
```

### View 執行任務模式（參考 VideoView）

```typescript
// 執行按鈕只負責 HTTP submit，不追蹤任務狀態
const isProcessing = ref(false)

async function executeConvert() {
  if (!fileId.value || isProcessing.value) return
  isProcessing.value = true
  try {
    const res = await fetch('/api/image/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId.value, output_format: fmt.value }),
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()

    taskStore.addTask({
      taskId: data.task_id,
      taskType: 'image.convert',
      status: 'pending',
      progress: 0,
      message: '',
      result: null,
      error: null,
      label: '圖片轉檔',
      fileName: currentFile.value?.name ?? '',
      createdAt: new Date(),
      updatedAt: new Date(),
    })
    toast.success('已提交轉檔任務')
  } catch (e) {
    toast.error(`提交失敗：${e}`)
  } finally {
    isProcessing.value = false  // 一定要在 finally 重置
  }
}

// 用 watch 監聽任務結果（與 isProcessing 完全分開）
watch(
  () => taskStore.tasks.get(currentTaskId.value),
  (task) => {
    if (task?.status === 'completed' && task.result?.output_file_id) {
      resultPreviewUrl.value = `/api/files/${task.result.output_file_id}/download`
    }
  },
  { deep: true }
)
```

### CSS / SCSS 規範

- 每個元件使用 `<style scoped lang="scss">`
- 顏色、字體、間距**必須**使用 CSS 變數，不 hardcode 顏色值
- 主要 CSS 變數（定義於 `assets/base.css`）：

```scss
// 背景
var(--bg-gradient-start), var(--bg-gradient-end)
var(--panel-bg), var(--panel-hover), var(--panel-active)
var(--panel-border)

// 文字
var(--text-primary), var(--text-secondary), var(--text-muted)

// 輸入框
var(--input-bg), var(--input-border)

// 主題色
var(--color-primary)       // 品牌藍
var(--color-success)       // 綠
var(--color-danger)        // 紅
var(--color-accent)        // 強調色
```

- 深色模式為預設，透過 `useTheme` composable 切換

---

## 二進位工具整合規範

新增需要外部執行檔的功能（如圖像處理工具）：

1. **放置位置**：`bin/<tool-name>/`（執行檔 + 必要模型/資源）
2. **路徑函數**：在 `core/paths.py` 新增 `get_<tool>_dir()` 函數
3. **可用性檢查**：Service 提供 `is_<tool>_available() -> bool` 方法
4. **狀態 API**：路由提供 `GET /api/<domain>/<tool>/status` 端點，前端據此決定是否顯示選項

```python
# core/paths.py 範例
def get_mytool_dir() -> Path:
    if _is_frozen():
        return Path(sys.executable).parent.parent / "mytool"
    else:
        return _get_app_root() / "bin" / "mytool"
```

---

## API 端點總覽

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/health` | 健康檢查 |
| GET | `/api/device` | GPU/CPU 資訊 |
| POST | `/api/files/upload` | 上傳檔案 |
| POST | `/api/files/register-local` | 註冊本地檔案（Electron） |
| GET | `/api/files/{id}` | 取得檔案資訊 |
| GET | `/api/files/{id}/download` | 下載檔案 |
| DELETE | `/api/files/{id}` | 刪除檔案 |
| GET | `/api/tasks` | 列出所有任務 |
| GET | `/api/tasks/{id}` | 取得任務狀態 |
| GET | `/api/tasks/{id}/progress` | SSE 進度串流 |
| POST | `/api/tasks/{id}/cancel` | 取消任務 |
| DELETE | `/api/tasks/{id}` | 移除任務 |
| GET | `/api/video/info/{file_id}` | 影片媒體資訊 |
| POST | `/api/video/transcode` | 影片轉檔 |
| POST | `/api/video/subtitle/generate` | 語音轉字幕 |
| POST | `/api/video/subtitle/translate` | 字幕翻譯 |
| GET | `/api/image/info/{file_id}` | 圖片資訊（寬/高/格式/模式） |
| POST | `/api/image/convert` | 圖片格式轉換 |
| GET | `/api/image/upscale/status` | 超解析引擎可用性 |
| POST | `/api/image/upscale` | 圖片超解析 |
| POST | `/api/audio/transcode` | 音訊轉換 |
| POST | `/api/document/translate` | 文件翻譯 |

---

## 開發環境

### 啟動

```bash
cd src/electron
npm run electron
```

自動啟動：Vite dev server (port 8000) + Python FastAPI (port 8001) + Electron

### 重啟

```bash
taskkill //F //IM electron.exe
taskkill //F //IM node.exe
taskkill //F //IM python.exe
# 等 2 秒後再啟動
cd src/electron && npm run electron
```

### Python 虛擬環境

```bash
# 執行單個腳本
.venv/Scripts/python.exe <script>

# 確認 import 正常（在 src/ 目錄下執行）
cd src && ../.venv/Scripts/python.exe -c "from backend.main import app; print('OK')"
```

---

## 打包（Production）

- Python 後端：PyInstaller，`core/paths.py` 的 `_is_frozen()` 自動切換路徑
- 前端：`npm run build` 產出靜態檔案
- Electron 打包：`npm run electron:build`
- 打包後二進位工具路徑：`resources/<tool-name>/`（相對於 `sys.executable` 父目錄的父目錄）
