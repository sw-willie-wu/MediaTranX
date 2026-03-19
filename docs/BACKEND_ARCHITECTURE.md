# 後端開發規範

> 所有後端新增與修改**必須**遵循此文件。違反規範的程式碼不應合併。

---

## 1. 分層規則

```
API 路由層 (api/routes/)     ← 只做參數驗證、呼叫 Service、回傳 Response
  api/schemas/               ← Pydantic response models（API 專用）
Service 業務層 (services/)    ← 協調 FileService + TaskManager，執行業務邏輯
Engine 底層封裝 (engine/)     ← AI 推理、硬體偵測、路徑解析、FFmpeg
Workers (workers/)            ← TaskManager、ProgressTracker
Models (models/)              ← 跨層共用 domain types（enum、dataclass）
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

---

## 2. Import 規則

### 2.1 Lazy Import（強制）

外部 AI 套件（PIL、numpy、torch、cv2、rembg、faster_whisper 等）**禁止** module-level import。
這些套件安裝在外部 `.venv`，首次啟動時可能尚未安裝，module-level import 會導致整個 app 啟動失敗。

```python
# ✗ 禁止
from PIL import Image
import numpy as np

class MyService:
    def _execute(self, params, progress_callback):
        img = Image.open(...)

# ✓ 正確：在方法內 import
class MyService:
    def _execute(self, params, progress_callback):
        from PIL import Image
        img = Image.open(...)
```

Python 會快取已 import 的模組（`sys.modules`），方法內重複 `from PIL import Image` 只是一次 dict lookup，無效能損失。

### 2.2 Type Hints 中使用外部套件

如果 type hints 引用了外部套件的型別（如 `img: Image.Image`），必須加 `from __future__ import annotations`，否則型別標註會在 class 定義時就觸發 import：

```python
from __future__ import annotations  # 延遲型別標註求值

class MyService:
    @staticmethod
    def _apply_filter(img: Image.Image) -> Image.Image:
        from PIL import Image  # 實際使用時才 import
        ...
```

### 2.3 內部模組 Import

內部模組（`app.services.*`、`app.engine.*`、`app.workers.*`、`app.api.*`）可以在 module-level import，因為它們是 Nuitka 編譯的一部分。

```python
# ✓ 這些可以 module-level
from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager
```

---

## 3. Service 規範

### 3.1 結構模板

每個 Service 必須遵循以下結構：

```python
"""
服務說明（一行）
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_XXX = "domain.action"  # e.g., "image.compress", "video.transcode"


class XxxService:
    """單例 Service"""
    _instance: Optional["XxxService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_XXX, self._handle_task)
        self._initialized = True
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
        from PIL import Image  # Lazy import

        progress_callback(0.1, "載入檔案...")
        # ... 業務邏輯 ...

        # 註冊輸出
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


# --- 工廠函數 ---

_xxx_service: Optional[XxxService] = None

def get_xxx_service() -> XxxService:
    global _xxx_service
    if _xxx_service is None:
        _xxx_service = XxxService()
    return _xxx_service
```

### 3.2 規則

- **單例模式**：使用 `__new__` + `_initialized` 守門，不使用其他單例實作
- **TASK_TYPE 常數**：格式為 `"domain.action"`（如 `"image.compress"`、`"audio.transcribe"`）
- **submit 方法**：`async`，驗證 file_id 存在後提交給 TaskManager，回傳 `task_id`
- **_handle_task**：同步方法，作為 TaskManager 的 handler callback，在 ThreadPoolExecutor 中執行
- **_execute**：實際業務邏輯，接收 `params` dict 和 `progress_callback`
- **progress_callback**：從 0.0 呼叫到 1.0，最終的結果由 TaskManager 自動 emit `stage="completed"`
- **結果 dict**：必須包含 `output_file_id`，前端依此取得處理結果

### 3.3 輸出路徑決定順序

```python
# 1. 使用者指定的 output_dir
# 2. 原始檔案的 source_dir（Electron 本地檔案的來源目錄）
# 3. FileService.output_dir（預設輸出目錄）

if custom_output_dir:
    output_dir = Path(custom_output_dir)
elif file_info.source_dir:
    output_dir = Path(file_info.source_dir)
else:
    output_dir = self._file_service.output_dir
```

---

## 4. Route 規範

### 4.1 結構模板

```python
"""
功能說明 API 路由
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.xxx import get_xxx_service

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
async def do_action(request: XxxRequest):
    """端點說明"""
    try:
        service = get_xxx_service()
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

## 5. 任務系統規範

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

## 6. 日誌規範

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

## 7. 路徑規範

### 7.1 所有路徑必須透過 `engine/paths.py`

```python
# ✗ 禁止 hardcode
path = Path("C:/Users/.../models/")

# ✓ 正確
from app.engine.paths import get_models_dir
path = get_models_dir("image")
```

### 7.2 路徑函數列表

| 函數 | Dev | Packaged |
|------|-----|----------|
| `get_base_data_dir()` | `core/backend/` | `%APPDATA%/MediaTranX/` |
| `get_models_dir(category)` | `backend/models/{cat}/` | `%APPDATA%/MediaTranX/models/{cat}/` |
| `get_temp_dir()` | `backend/temp/` | `%APPDATA%/MediaTranX/temp/` |
| `get_output_dir()` | `backend/output/` | `backend/output/`（或 APPDATA） |
| `get_venv_dir()` | `backend/.venv/` | `%APPDATA%/MediaTranX/.venv/` |
| `get_ffmpeg_dir()` | `bin/ffmpeg/` | `resources/ffmpeg/` |
| `get_llama_bin_dir()` | `bin/llama/` | `resources/llama-bin/` |

### 7.3 新增外部工具

1. 在 `engine/paths.py` 新增 `get_xxx_dir()` 函數
2. Dev 模式放 `bin/<tool>/`，打包後放 `resources/<tool>/`
3. Service 提供 `is_xxx_available() -> bool` 檢查

---

## 8. 錯誤處理規範

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

## 9. 命名規範

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

## 10. 新增功能 Checklist

新增一個處理功能時，按順序完成：

1. [ ] **Service**：在 `services/{domain}/` 新增 `{action}_service.py`，遵循 §3 模板
2. [ ] **Route**：在 `api/routes/{domain}/` 新增 `{action}.py`，遵循 §4 模板
3. [ ] **註冊 Route**：在 `api/routes/{domain}/__init__.py` include 新 router
4. [ ] **Lazy Import**：確認所有外部套件（PIL 等）都在方法內 import
5. [ ] **Type Hints**：如果 type hints 用了外部套件型別，加 `from __future__ import annotations`
6. [ ] **日誌**：Service 初始化和任務提交/完成有 `logger.info`
7. [ ] **路徑**：所有路徑透過 `engine/paths.py` 取得
8. [ ] **文件**：更新 `docs/ARCHITECTURE.md` 的相關段落（API 總覽、View 結構等）

### 新增 AI 模型

1. [ ] 在 `engine/ai/registry.py` 新增模型定義
2. [ ] 在 `engine/ai/{format}/` 新增 Runtime 實作
3. [ ] 在 Service 的 `_execute` 方法中透過 ModelManager 呼叫
