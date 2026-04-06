# 後端開發規範

> 所有後端新增與修改**必須**遵循此文件。違反規範的程式碼不應合併。

---

## 1. 分層規則

```
app/
├── init/                      ← 啟動初始化（DLL 注入、日誌、相容層）
├── api/
│   ├── routes/                ← 路由層：參數驗證 → 呼叫 Service → 回傳 Response
│   └── schemas/               ← Pydantic response models（API 專用）
├── db/                        ← 資料庫層（SQLModel）
│   ├── database.py            ← Engine 建立、migration
│   ├── models/                ← ORM models（api_connection、task_history）
│   └── dao/                   ← Data Access Objects
├── services/                  ← 業務層：協調 FileService + TaskManager
├── engine/                    ← 底層封裝
│   ├── paths.py               ← 路徑管理
│   ├── device.py              ← GPU/CPU 偵測
│   ├── ffmpeg.py              ← FFmpeg 操作
│   └── ai/                    ← AI 模型
│       ├── runtime/           ← Runtime 基礎類別（base、package、pth、llama_server）
│       ├── image/             ← 影像模型（realesrgan、codeformer、mobilesam 等）
│       ├── audio/             ← 語音模型（whisper、demucs、wav2vec2）
│       ├── llama/             ← LLM（gemma、qwen3、vlm、translate prompt）
│       ├── remote/            ← 遠端 API Provider（ollama、openai、gemini）
│       ├── registry.py        ← 模型註冊表
│       └── model_manager.py   ← VRAM / Slot 管理
├── workers/                   ← TaskManager、ProgressTracker
├── models/                    ← 跨層共用 domain types（enum、dataclass）
├── utils/                     ← 工具函數（gif_utils）
└── exceptions.py              ← 自訂例外階層
```

### 禁止事項

- **Route 不可**直接操作檔案、呼叫 AI 模型、import PIL/numpy/torch
- **Service 不可**直接操作 VRAM 或啟動 subprocess，必須透過 Engine
- **Engine 不可**包含業務邏輯（不知道「壓縮」「轉檔」的概念，只提供技術能力）
- **不可跨層跳躍**：Route → Engine ✗，必須經過 Service
- **Workers 不可**依賴 API 層：Workers → `app.api.*` ✗

### 跨層共用型別

跨層共用的 domain models 放在 `app/models/`（純 Python dataclass + enum），避免 workers/services 反向依賴 API 層：

```
app/models/
  task.py   ← TaskStatus (enum) + TaskData (dataclass)
  file.py   ← FileData (dataclass)
```

API 層的 Pydantic models（`TaskResponse`、`FileInfo`）在 `api/schemas/common.py`，routes 透過 `from_task_data()` / `from_file_data()` 轉換。

### 資料庫層（app/db/）

使用 SQLModel（Pydantic + SQLAlchemy），SQLite 儲存：

- `db/database.py` — Engine 建立、WAL 模式、自動 migration（ALTER TABLE 補欄位）
- `db/models/` — ORM models：`ApiConnection`（遠端 API 連線）、`TaskHistory`（任務歷史）
- `db/dao/` — DAO pattern 封裝 CRUD，Service 不直接寫 SQL

```python
# DAO 使用範例
from app.db.dao.api_connection_dao import ApiConnectionDAO
dao = ApiConnectionDAO()
conn = dao.create(provider="ollama", name="Local", endpoint="http://localhost:11434")
```

### 自訂例外（app/exceptions.py）

```
MediaTranXError
├── ModelNotFoundError     ← 模型未找到
├── ModelLoadError         ← 模型載入失敗
├── InferenceError         ← AI 推論錯誤
├── TaskError              ← 任務執行錯誤
├── FileNotFoundError_     ← 檔案未找到
├── ConfigError            ← 設定錯誤
└── RemoteApiError         ← 雲端 API 錯誤（帶 error code 供前端 i18n）
```

`RemoteApiError` 包含 `code` 欄位（如 `gpu_oom`、`quota_exceeded`），TaskManager 會存入 `error_code`，前端用 `t('tasks.errors.{code}')` 翻譯。

### 遠端 API Provider（engine/ai/remote/）

```
remote/
├── base.py      ← RemoteProvider 抽象基底（connect、list_models、chat）
├── ollama.py    ← OllamaProvider（/api/chat、/api/tags、/api/show）
├── openai.py    ← OpenAIProvider（Chat Completions + Responses API）
└── gemini.py    ← GeminiProvider（generateContent）
```

- 每個 Provider 實作 `connect()`、`list_models()`、`chat()`
- `chat()` 支援 vision messages（各 provider 格式不同，內部轉換）
- 模型 capabilities 從 API 偵測（Ollama: `/api/show`、OpenAI: 已知表、Gemini: `supportedGenerationMethods`）
- 錯誤統一拋 `RemoteApiError(code, detail)`

---

## 2. 模型 Metadata i18n 規範（強制）

`model_metadata_service.py` 中所有面向前端的 `description` 欄位**禁止**使用中文或英文硬編碼字串。必須使用 i18n key，由前端負責翻譯。

```python
# ✗ 禁止
{"label": "Real-ESRGAN", "description": "通用超解析（寫實）"}
{"label": "Real-ESRGAN", "description": "General Super-Resolution"}

# ✓ 正確：使用 i18n key
{"label": "Real-ESRGAN", "description": "models.realesrgan"}
```

- `label` 使用模型英文名稱（如 `Real-ESRGAN`、`Whisper Large-v3`），不需翻譯
- `description` 使用 `models.<key>` 格式的 i18n key
- 複合描述用 `||` 分隔（如 `"models.size.light_fast||models.quant.q4km"`），前端以 ` · ` 合併顯示
- 新增模型時必須同時在 `en.ts` 和 `zh-TW.ts` 的 `models` 區塊加入對應翻譯

---

## 3. Import 規則

### 3.1 Top-Level Import（預設）

所有套件（含 AI 套件如 PIL、numpy、torch）在 Electron 啟動時由 `uv sync` 安裝完成，可直接 top-level import。

```python
# ✓ 正確：直接 top-level import
from PIL import Image
import numpy as np
import torch

class MyService:
    def _execute(self, params, progress_callback):
        img = Image.open(...)
```

### 3.2 例外：偵測性質的 Import

僅在偵測是否可用的場景中使用 lazy import（try/except 內）：

```python
# ✓ 偵測用途，保留 lazy import
def _detect_cuda_via_torch():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False
```

### 3.3 Type Hints

直接使用外部套件型別，不需要 `from __future__ import annotations`：

```python
from PIL import Image

class MyService:
    @staticmethod
    def _apply_filter(img: Image.Image) -> Image.Image:
        ...
```

---

## 4. Service 規範

### 4.1 結構模板

Service 由 DI Container（`dependency-injector`）管理為 Singleton，不使用手動工廠函數。

```python
"""
服務說明（一行）
"""
import logging
from pathlib import Path
from typing import Callable
from uuid import uuid4

from PIL import Image  # Top-level import（AI 套件已由 Electron 安裝）

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_XXX = "domain.action"  # e.g., "image.compress", "video.transcode"


class XxxService:
    """由 DI Container 管理的 Singleton Service"""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(TASK_TYPE_XXX, self._handle_task)
        logger.info("XxxService initialized")

    # --- 公開 API（Route 呼叫）---

    async def submit_xxx(self, file_id: str, **params) -> str:
        """驗證輸入 → 提交任務 → 回傳 task_id"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        task_id = await self._task_manager.submit(TASK_TYPE_XXX, {
            "file_id": file_id,
            **params,
        })
        logger.info(f"Task submitted: {task_id}")
        return task_id

    # --- 任務 Handler（ThreadPoolExecutor 內執行）---

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        progress_callback(0.1, "載入檔案...")
        # ... 業務邏輯 ...

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "處理完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
        }
```

**DI Container 註冊**（`app/init/container.py`）：
```python
from app.services.xxx import XxxService

class AppContainer(containers.DeclarativeContainer):
    xxx_service = providers.Singleton(
        XxxService,
        file_service=file_service,
        task_manager=task_manager,
    )
```

### 4.2 規則

- **DI Singleton**：由 AppContainer 管理生命週期，不使用手動 `__new__` 單例或工廠函數
- **建構子注入**：依賴（FileService、TaskManager）透過 `__init__` 參數注入
- **TASK_TYPE 常數**：格式為 `"domain.action"`（如 `"image.compress"`、`"audio.transcribe"`）
- **submit 方法**：`async`，驗證 file_id 存在後提交給 TaskManager，回傳 `task_id`
- **_handle_task**：同步方法，作為 TaskManager 的 handler callback，在 ThreadPoolExecutor 中執行
- **_execute**：實際業務邏輯，接收 `params` dict 和 `progress_callback`
- **progress_callback**：從 0.0 呼叫到 1.0，最終的結果由 TaskManager 自動 emit `stage="completed"`
- **結果 dict**：必須包含 `output_file_id`，前端依此取得處理結果

### 3.3 輸出路徑決定順序

處理結果一律先存到暫存目錄，使用者確認後透過下載按鈕自行儲存到目標位置。

```python
# 1. 使用者指定的 output_dir（如有）
# 2. FileService.output_dir（預設 temp/results）

output_dir = Path(custom_output_dir) if custom_output_dir else self._file_service.output_dir
```

---

## 5. Route 規範

### 4.1 結構模板

```python
"""
功能說明 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from dependency_injector.wiring import inject, Provide

from app.init.container import AppContainer
from app.services.xxx import XxxService

router = APIRouter()


class XxxRequest(BaseModel):
    """請求模型"""
    file_id: str = Field(..., description="輸入檔案 ID")
    option: str = Field(default="default", description="選項說明")


class XxxResponse(BaseModel):
    """回應模型"""
    task_id: str
    message: str = "任務已提交"


@router.post("/action", response_model=XxxResponse)
@inject
async def do_action(
    request: XxxRequest,
    service: XxxService = Depends(Provide[AppContainer.xxx_service]),
):
    """端點說明"""
    try:
        task_id = await service.submit_xxx(
            file_id=request.file_id,
            option=request.option,
        )
        return XxxResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 4.2 規則

- Request/Response 模型定義在 route 檔案內，不放到 `schemas/common.py`（除非多個 route 共用）
- `Field(...)` 表示必填，`Field(default=...)` 表示選填
- 錯誤處理：`ValueError` → 404，其他 → 500
- Route 內**不可**有業務邏輯，只做：驗證 → 呼叫 Service → 回傳
- 新 route 必須在對應的 `routes/{domain}/__init__.py` 中 include

### 4.3 路由註冊

```python
# routes/image/__init__.py
from .compress import router as compress_router

router = APIRouter(prefix="/image", tags=["image"])
router.include_router(compress_router)
```

---

## 6. 任務系統規範

### 5.1 任務狀態

```
PENDING → PROCESSING → COMPLETED
                     → FAILED
                     → CANCELLED
```

### 5.2 Progress Callback 使用

```python
def _execute(self, params, progress_callback):
    progress_callback(0.1, "載入檔案...")      # 階段描述
    progress_callback(0.5, "處理中...")
    progress_callback(0.9, "儲存檔案...")
    progress_callback(1.0, "完成")              # 最終必須到 1.0
    return {"output_file_id": ...}              # 必須回傳 dict
```

- progress 值必須遞增（0.0 → 1.0）
- message 使用中文，為使用者可讀的階段描述
- TaskManager 在 handler return 後自動 emit `stage="completed"` + `result`

### 5.3 前端 Polling

前端透過 `GET /api/tasks/active` 每秒輪詢進行中的任務，ProgressTracker 儲存最新的 ProgressEvent 供查詢。

---

## 7. 日誌規範

### 6.1 Logger 建立

每個模組使用 `logging.getLogger(__name__)`：

```python
logger = logging.getLogger(__name__)
```

### 6.2 日誌等級

| 等級 | 用途 |
|------|------|
| `DEBUG` | 進度追蹤、中間變數（production 不輸出） |
| `INFO` | Service 初始化、任務提交/完成、模型載入 |
| `WARNING` | 非致命異常（如模型未找到、fallback 行為） |
| `ERROR` | 任務失敗、啟動失敗、不可恢復的錯誤 |

### 6.3 日誌輸出

| 環境 | 輸出位置 |
|------|---------|
| Dev | stdout（Electron pipe → `data/dev_backend.log`） |
| Production | stdout → `logs/app.log`（Electron pipe），WARNING+ → `logs/core_error.log`（Python FileHandler） |

---

## 8. 路徑規範

### 7.1 所有路徑透過 `PathSettings`（pydantic-settings）

路徑由 Electron 透過 `MEDIATRANX_*` 環境變數注入，Python 的 `PathSettings` 讀取。Dev 模式下使用預設值（`core/backend/` 子目錄）。

```python
# ✗ 禁止 hardcode
path = Path("C:/Users/.../models/")

# ✓ 正確：透過 settings
from app.init.configs import get_settings
settings = get_settings()
path = Path(settings.path.models) / "image"
```

### 7.2 路徑欄位

| 欄位 | Dev 預設值 | Electron 覆蓋（env var） |
|------|-----------|------------------------|
| `path.data` | `core/backend/` | `MEDIATRANX_DATA` → `%APPDATA%/MediaTranX/` |
| `path.venv` | `core/backend/.venv` | `MEDIATRANX_VENV` |
| `path.bin` | `core/backend/bin` | `MEDIATRANX_BIN` |
| `path.models` | `core/backend/models` | `MEDIATRANX_MODELS` |
| `path.temp` | `core/backend/data/temp` | `MEDIATRANX_TEMP` |
| `path.ffmpeg` | 衍生自 `bin/ffmpeg` | — |
| `path.fluidsynth` | 衍生自 `bin/fluidsynth` | — |
| `path.llama_bin` | 衍生自 `bin/llama` | — |

### 7.3 新增外部工具

1. 在 `PathSettings` 新增衍生 property（從 `bin` 計算）
2. Dev 模式放 `bin/<tool>/`
3. Electron 首次啟動時下載到 `{MEDIATRANX_BIN}/<tool>/`

---

## 9. 錯誤處理規範

### 8.1 Service 層

```python
# submit 方法：驗證失敗拋 ValueError
async def submit_xxx(self, file_id: str, ...) -> str:
    file_info = self._file_service.get_file(file_id)
    if file_info is None:
        raise ValueError(f"File not found: {file_id}")

# execute 方法：讓異常自然拋出，TaskManager 會捕獲並設定 FAILED 狀態
def _execute(self, params, progress_callback):
    # 不需要 try/except，TaskManager._execute_task() 統一處理
    ...
```

### 8.2 Route 層

```python
try:
    task_id = await service.submit_xxx(...)
    return XxxResponse(task_id=task_id)
except ValueError as e:
    raise HTTPException(status_code=404, detail=str(e))
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

### 8.3 Engine 層

Engine 方法失敗時直接拋異常，由上層 Service/TaskManager 處理。不吞異常。

---

## 10. 命名規範

### 9.1 檔案命名

| 位置 | 格式 | 範例 |
|------|------|------|
| Service | `{action}_service.py` | `compress_service.py` |
| Route | `{action}.py` | `compress.py` |
| Engine AI | `{model_name}.py` | `realesrgan.py` |

### 9.2 Class 命名

| 位置 | 格式 | 範例 |
|------|------|------|
| Service | `{Domain}{Action}Service` | `ImageCompressService` |
| Route Request | `{Action}Request` | `ImageCompressRequest` |
| Route Response | `{Action}Response` | `ImageCompressResponse` |

### 9.3 常數命名

```python
TASK_TYPE_IMAGE_COMPRESS = "image.compress"
TASK_TYPE_VIDEO_TRANSCODE = "video.transcode"
```

### 9.4 工廠函數

```python
def get_image_compress_service() -> ImageCompressService:
    ...
```

---

## 11. 新增功能 Checklist

新增一個處理功能時，按順序完成：

1. [ ] **Service**：在 `services/{domain}/` 新增 `{action}_service.py`，遵循 §4 模板
2. [ ] **DI 註冊**：在 `app/init/container.py` 的 AppContainer 註冊 Singleton
3. [ ] **Route**：在 `api/routes/{domain}/` 新增 `{action}.py`，遵循 §5 模板（DI injection）
4. [ ] **註冊 Route**：在 `api/routes/{domain}/__init__.py` include 新 router
5. [ ] **Import**：外部套件直接 top-level import
6. [ ] **日誌**：Service 初始化和任務提交/完成有 `logger.info`
7. [ ] **路徑**：所有路徑透過 `get_settings().path` 取得
8. [ ] **文件**：更新 `docs/ARCHITECTURE.md` 的相關段落

### 新增本地 AI 模型

1. [ ] 在 `engine/ai/registry.py` 新增模型定義
2. [ ] 在 `engine/ai/{category}/` 新增 Wrapper（繼承對應 Runtime）
   - `image/` — PTHRuntime（torch state_dict 載入）
   - `audio/` — PackageRuntime（第三方套件自帶載入）
   - `llama/` — LlamaServerRuntime（llama-server subprocess）
3. [ ] 在 Service 的 `_execute` 方法中透過 ModelManager 呼叫

### 新增遠端 API Provider

1. [ ] 在 `engine/ai/remote/` 新增 `{provider}.py`，繼承 `RemoteProvider`
2. [ ] 實作 `connect()`、`list_models()`、`chat()`
3. [ ] 在 `remote/__init__.py` 匯出
4. [ ] 在 `services/setup/remote_service.py` 的 `_get_provider()` 加入分支
5. [ ] 前端 `ModelDownloadManager.vue` 的 `providerOptions` 加入選項
