# 後端開發規範

> 所有後端新增與修改**必須**遵循此文件。違反規範的程式碼不應合併。

---

## 1. 分層規則

```
app/
├── init/                      ← 啟動初始化（DLL 注入、日誌、相容層）
├── api/
│   ├── routes/                ← 路由層：參數驗證 → 呼叫 Service → 回傳 Response
│   └── (Response models defined in route files directly)
├── db/                        ← 資料庫層（SQLModel）
│   ├── database.py            ← Engine 建立、migration
│   ├── models/                ← ORM models（api_connection、task_history）
│   └── dao/                   ← Data Access Objects
├── services/                  ← 業務層：協調 FileService + TaskManager
├── engine/                    ← 底層封裝
│   ├── paths.py               ← 路徑管理
│   ├── device.py              ← GPU/CPU 偵測
│   ├── ffmpeg.py              ← FFmpegWrapper（cut / extract_audio / audio_convert / adjust_volume / transcode）
│   └── ai/                    ← AI 模型
│       ├── runtime/           ← Runtime 基礎類別（base、package、pth、llama_server）
│       ├── image/             ← 影像模型（realesrgan、codeformer、mobilesam 等）
│       ├── audio/             ← 語音模型（whisper、demucs、wav2vec2）
│       ├── llama/             ← LLM（gemma、qwen3、vlm、translate prompt）
│       ├── remote/            ← 遠端 API Provider（ollama、openai、gemini）
│       ├── registry.py        ← 模型註冊表（含推理參數 inference config）
│       └── model_manager.py   ← VRAM / Slot 管理
├── workers/                   ← TaskManager、ProgressTracker
├── schemas/                   ← 跨層共用 domain types（enum、dataclass）
├── utils/                     ← 工具函數（inference、prompts、translate、summarize）
└── exceptions.py              ← 自訂例外階層
```

### 禁止事項

- **Route 不可**直接操作檔案、呼叫 AI 模型、import PIL/numpy/torch
- **Service 不可**直接操作 VRAM 或啟動 subprocess，必須透過 Engine / Utils
  - FFmpeg 操作：使用 `engine/ffmpeg.py` 的 `FFmpegWrapper.cut()` / `.extract_audio()` / `.audio_convert()` / `.adjust_volume()` / `.transcode()`
  - 影片 Frame Pipe：使用 `utils/video_frames.py` 的 `FramePipe`
- **Engine 不可**包含業務邏輯（不知道「壓縮」「轉檔」的概念，只提供技術能力）
- **不可跨層跳躍**：Route → Engine ✗，必須經過 Service
- **Workers 不可**依賴 API 層：Workers → `app.api.*` ✗

### 跨層共用型別

跨層共用的 domain types 放在 `app/schemas/`（純 Python dataclass + enum），避免 workers/services 反向依賴 API 層：

```
app/schemas/
  task.py   ← TaskStatus (enum) + TaskData (dataclass)
  file.py   ← FileData (dataclass)
```

API 層的 Pydantic models（`TaskResponse`、`FileInfo`）直接定義在對應的 route 檔案中（`routes/tasks/active.py`、`routes/files.py`），透過 `from_task_data()` / `from_file_data()` 轉換。

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

## 3. Import 規則（Cold Start 優化）

為加速啟動（cold start 從 37 秒降至 ~8 秒），採用 **lazy container + TYPE_CHECKING** 模式，避免 module-level 觸發大量 import chain。

### 3.1 Service / Engine 檔案

AI 套件（PIL、numpy、torch 等）在 Electron 啟動時由 `uv sync` 安裝完成，可直接 top-level import。這些檔案在容器首次 resolve 時才被載入，不影響啟動速度。

```python
# ✓ 正確：Service / Engine 內直接 top-level import
from PIL import Image
import numpy as np
import torch

class MyService:
    def _execute(self, params, progress_callback):
        img = Image.open(...)
```

### 3.2 Container（`container.py`）

Domain service 使用 `_lazy()` factory 延遲 import，避免在 container 模組載入時觸發所有 service 的 import chain：

```python
# ✓ 正確：_lazy() 延遲 import
image_upscale = providers.Singleton(
    _lazy("app.services.image.upscale_service", "ImageUpscaleService"),
    file_service=file_service, task_manager=task_manager,
)

# ✗ 禁止：直接 import 會拖慢啟動
from app.services.image.upscale_service import ImageUpscaleService
image_upscale = providers.Singleton(ImageUpscaleService, ...)
```

### 3.3 Route 檔案

Domain service 的 import 放在 `TYPE_CHECKING` guard 內，搭配 `from __future__ import annotations` 讓型別標注在 runtime 不求值。這樣 route 模組載入時不會觸發 service import chain：

```python
# ✓ 正確：Route 檔案的 service import
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.image.upscale_service import ImageUpscaleService

router = APIRouter()

@router.post("/upscale")
@inject
async def upscale_image(
    request: UpscaleRequest,
    service: ImageUpscaleService = Depends(Provide[AppContainer.image_upscale]),
):
    ...
```

### 3.4 Engine `__init__.py`

Engine 的 `__init__.py` **不可**在 module level 直接 re-export wrapper class（會觸發整條 import chain）。消費者直接從具體模組 import。工廠函數內使用 lazy import：

```python
# ✗ 禁止：__init__.py 中 eagerly re-export
from .realesrgan import RealESRGANWrapper   # 觸發 torch import chain

# ✓ 正確：消費者直接 import 具體模組
from app.engine.ai.image.realesrgan import RealESRGANWrapper

# ✓ 正確：工廠函數使用 lazy import
def get_upscaler(model_id: str):
    if model_id == "realesrgan":
        from app.engine.ai.image.realesrgan import RealESRGANWrapper
        return RealESRGANWrapper(...)
```

### 3.5 偵測性質的 Import

僅在偵測是否可用的場景中使用 try/except lazy import：

```python
# ✓ 偵測用途，保留 lazy import
def _detect_cuda_via_torch():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False
```

---

## 4. Service 規範

### 4.1 結構模板

Service 由 DI Container（`dependency-injector`）管理為 Singleton，不使用手動 `__new__` 單例或工廠函數。

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
        file_info = self._file_service.require_file(file_id)  # raises FileNotFoundError_ → 404

        task_id = await self._task_manager.submit(TASK_TYPE_XXX, {
            "file_id": file_id,
            **params,
        })
        logger.info(f"Task submitted: {task_id}")
        return task_id

    # --- 任務 Handler（ThreadPoolExecutor 內執行）---

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        """薄 wrapper，由 TaskManager 呼叫。直接委派給 _execute。"""
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        """實際業務邏輯。"""
        progress_callback(0.1, "task.progress.loading_image")
        # ... 業務邏輯 ...

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.xxx_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
        }
```

> **多任務型別的 Service**：若一個 Service 處理多種任務（如 `video.cut` + `video.transcode`），
> 每種任務使用獨立的 handler/execute 對：`_handle_cut_task` + `_execute_cut`、
> `_handle_transcode_task` + `_execute_transcode`。

**DI Container 註冊**（`app/init/container.py`）：
```python
# ✓ 使用 _lazy() 延遲 import（參見 §3.2）
class AppContainer(containers.DeclarativeContainer):
    xxx_service = providers.Singleton(
        _lazy("app.services.xxx", "XxxService"),
        file_service=file_service,
        task_manager=task_manager,
    )
```

### 4.2 規則

- **DI Singleton**：由 AppContainer 以 `_lazy()` 註冊管理生命週期，不使用手動 `__new__` 單例或工廠函數
- **建構子注入**：依賴（FileService、TaskManager）透過 `__init__` 參數注入
- **TASK_TYPE 常數**：格式為 `"domain.action"`（如 `"image.compress"`、`"audio.transcribe"`）
- **submit 方法**：`async`，驗證 file_id 存在後提交給 TaskManager，回傳 `task_id`
- **_handle_task + _execute**：標準方法名。`_handle_task` 是 TaskManager 的 handler callback（同步，在 ThreadPoolExecutor 中執行），薄 wrapper 委派給 `_execute`
- **多任務型別**：Service 有多種任務時，使用 `_handle_{variant}_task` + `_execute_{variant}`（如 `_handle_cut_task` + `_execute_cut`）
- **progress_callback**：從 0.0 呼叫到 1.0，最終的結果由 TaskManager 自動 emit `stage="completed"`
- **結果 dict**：必須包含 `output_file_id`，前端依此取得處理結果

### 4.3 輸出路徑（temp-first policy）

Service **只**寫到 `FileService.output_dir`（預設 `temp/results/`），不接受 `output_dir` / `output_filename` 參數。使用者要把成果存出去時在前端透過 `useFileDownload.downloadFile`（單檔）或 `downloadBatch`（批次）自己選目的地。

```python
output_path = self._file_service.output_dir / new_filename
```

Results drawer 會讀取 `FileService.get_output_files()`（sidecar 持久化，見 §6.5–6.6），Settings 的「清除暫存」呼叫 `POST /files/cleanup` 一次清光。

---

## 5. Route 規範

### 5.1 結構模板

```python
"""
功能說明 API 路由
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
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
    task_id = await service.submit_xxx(
        file_id=request.file_id,
        option=request.option,
    )
    return XxxResponse(task_id=task_id)
```

### 5.2 規則

- Request/Response 模型定義在 route 檔案內
- `Field(...)` 表示必填，`Field(default=...)` 表示選填
- **錯誤處理**：Routes **不寫 try/except**；由全域 exception handler（`handler/error_responses.py`）統一處理：
  - `FileNotFoundError_` / `ModelNotFoundError` → 404
  - `ValueError` (參數驗證失敗) → 400
  - `RemoteApiError` → 502
  - `FFmpegError` / `MediaTranXError` / 其他 → 500
- Route 內**不可**有業務邏輯，只做：驗證 → 呼叫 Service → 回傳
- 新 route 必須在對應的 `routes/{domain}/__init__.py` 中 include

### 5.3 路由註冊

```python
# routes/image/__init__.py
from .compress import router as compress_router

router = APIRouter(prefix="/image", tags=["image"])
router.include_router(compress_router)
```

---

## 6. 任務系統規範

### 6.1 任務狀態

```
PENDING → PROCESSING → COMPLETED
                     → FAILED
                     → CANCELLED
```

### 6.2 Progress Callback 使用

```python
def _execute(self, params, progress_callback):
    progress_callback(0.1, "task.progress.loading_image")
    progress_callback(0.5, "task.progress.processing")
    progress_callback(0.9, "task.progress.saving_file")
    progress_callback(1.0, "task.progress.complete")
    return {"output_file_id": ...}
```

- progress 值必須遞增（0.0 → 1.0）
- message 使用 `task.progress.*` 格式的 i18n key，**禁止硬編碼中文或英文**
- 動態參數以 `|` 分隔：`f"task.progress.cropping|{idx + 1}|{total}"`
- 前端 `TasksActive.vue` 偵測 `task.progress.` 前綴後自動翻譯
- 新增 key 時必須同步更新 `en.ts` 和 `zh-TW.ts` 的 `task.progress` 區塊
- TaskManager 在 handler return 後自動 emit `stage="completed"` + `result`

### 6.3 Progress i18n Key 命名慣例

| 格式 | 範例 |
|------|------|
| 靜態訊息 | `task.progress.aligning` |
| 帶動態參數 | `f"task.progress.cropping\|{idx}\|{total}"` |
| 分類前綴 | `loading_*`（載入模型）、`*_complete`（完成）、`*_starting`（開始） |

### 6.4 前端 Polling

前端透過 `GET /api/tasks/active` 每秒輪詢進行中的任務，ProgressTracker 儲存最新的 ProgressEvent 供查詢。

### 6.5 Output Policy（Results Drawer 分流）

`TaskManager.register_handler` 必須宣告產出歸屬：

```python
task_manager.register_handler("image.upscale", handler, output_policy="history")
task_manager.register_handler("audio.transcribe", handler, output_policy="results")
```

| 值 | 語意 | 前端行為 |
|----|------|---------|
| `"history"` | 同類型單檔產出（in-place 迭代） | 進 filmstrip / historyStack |
| `"results"` | 跨類型 or 多檔 or 新產物 | 進 Results Drawer（右上產出抽屜） |

規則：
- **輸出類型 ≠ 輸入類型** ⋁ **多檔產出** → 必須宣告 `"results"`
- 若宣告 `"history"` 但 runtime 產出多檔 / 跨類型 → TaskManager 自動 downgrade 為 `"results"` + 發出 warning（提示開發者修正 register_handler）
- MIDI 渲染這類「同類型但語意上是新產物」要顯式宣告 `"results"`

### 6.6 Sidecar 持久化

Results-policy 的產出會由 `FileService.tag_as_result` 寫入 sidecar `<file_id>.meta.json`，後端啟動時 `scan_output_dir()` 從 sidecar 還原 `_files`，讓 Drawer 跨 session 保留。`saved_path`（使用者另存位置）透過 `PATCH /files/{id}/saved-path` 寫入同一份 sidecar。

---

## 7. 日誌規範

### 7.1 Logger 建立

每個模組使用 `logging.getLogger(__name__)`：

```python
logger = logging.getLogger(__name__)
```

### 7.2 日誌等級

| 等級 | 用途 |
|------|------|
| `DEBUG` | 進度追蹤、中間變數（production 不輸出） |
| `INFO` | Service 初始化、任務提交/完成、模型載入 |
| `WARNING` | 非致命異常（如模型未找到、fallback 行為） |
| `ERROR` | 任務失敗、啟動失敗、不可恢復的錯誤 |

### 7.3 日誌輸出

| 環境 | 輸出位置 |
|------|---------|
| Dev | stdout（Electron pipe → `data/dev_backend.log`） |
| Production | stdout → `logs/app.log`（Electron pipe），WARNING+ → `logs/core_error.log`（Python FileHandler） |

---

## 8. 路徑規範

### 8.1 所有路徑透過 `PathSettings`（pydantic-settings）

路徑由 Electron 透過 `MEDIATRANX_*` 環境變數注入，Python 的 `PathSettings` 讀取。Dev 模式下使用預設值（`core/backend/` 子目錄）。

```python
# ✗ 禁止 hardcode
path = Path("C:/Users/.../models/")

# ✓ 正確：透過 settings
from app.init.configs import get_settings
settings = get_settings()
path = Path(settings.path.models) / "image"
```

### 8.2 路徑欄位

Top-level（可 env override）：

| 欄位 | Dev 預設值 | env var |
|------|-----------|---------|
| `path.root` | `.` (cwd) | `MEDIATRANX_PATH__ROOT` → `%APPDATA%/MediaTranX/` |
| `path.models` | `models` | `MEDIATRANX_PATH__MODELS` |
| `path.temp` | `temp` | `MEDIATRANX_PATH__TEMP` |

Computed fields（從 `root` 衍生，無 env override）：

| 欄位 | 衍生 |
|------|------|
| `path.venv` | `root/.venv` |
| `path.log` | `root/logs` |
| `path.ffmpeg` | `root/bin/ffmpeg`（Win）/ `ffmpeg`（其他） |
| `path.llama` | `root/bin/llama` |
| `path.soundfonts` | `root/bin/soundfonts/musyngkite` |

### 8.3 新增外部工具

1. 在 `PathSettings` 新增 `@computed_field`（從 `root/bin` 計算）
2. Dev 模式放 `bin/<tool>/`
3. Electron 首次啟動時下載到 `<root>/bin/<tool>/`

---

## 9. LLM 推理參數化

### 9.1 架構

LLM 推理參數（temperature、top_k、top_p、max_tokens、prompt）不硬編碼在 service 中，統一由以下模組管理：

```
registry.py          → 每個模型 family 的 inference config（per-task 採樣參數 + prompt builder）
utils/inference.py   → get_inference_config()、calc_max_tokens()、calc_batch_size()
utils/prompts.py     → get_prompt_builder()（per-model prompt builder dispatch）
```

### 9.2 Registry inference config

每個 GGUF model family 在 `registry.py` 定義 `inference` block（family level）和 n_ctx range（spec level）：

```python
"qwen3": {
    "inference": {
        "translate": {
            "temperature": 0.1, "top_k": 40, "top_p": 0.9,
            "prompt_builder": "qwen3", "thinking": False,
            "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 4, "max_tokens_cap": 16384,
        },
        "summarize": { ... },
    },
    "specs": {
        "8b": {
            "n_ctx_min": 4096, "n_ctx_max": 32768, "n_ctx_default": 16384,
            "vram_per_ctx_token": 0.04,
            ...
        },
    },
}
```

Remote providers 使用 `REMOTE_INFERENCE_DEFAULTS`（固定 temperature + max_tokens）。

### 9.3 Service 呼叫流程

```python
from app.utils.inference import get_inference_config, calc_max_tokens, estimate_tokens
from app.utils.prompts import get_prompt_builder

config = get_inference_config(model_family, model_size, "translate")
builder = get_prompt_builder("translate", config["prompt_builder"], thinking=config.get("thinking", False))
result = builder(text, source_lang, target_lang, format, style, glossary)

max_tokens = calc_max_tokens(config, config["n_ctx"], estimate_tokens(text))

if result["mode"] == "chat":
    output = runtime.chat(messages=result["messages"], max_tokens=max_tokens,
                          temperature=config["temperature"], top_k=config["top_k"], top_p=config["top_p"])
elif result["mode"] == "completion":
    output = runtime.complete(prompt=result["prompt"], ...)
```

### 9.4 Prompt builder

每個模型 family 有對應的 prompt builder，處理 chat template 差異：

| Builder | 特徵 |
|---------|------|
| `default` | 標準 system + user role |
| `qwen3` | 加 `/no_think` 後綴（thinking=False 時） |
| `gemma` | 無 system role，合併到 user message |

### 9.5 Thinking 控制

- Registry 定義預設值（`"thinking": False`）
- API 請求可覆蓋（`thinking` 參數）
- `thinking=False`：Qwen3 builder 加 `/no_think`
- `thinking=True`：使用 default builder（不加 `/no_think`）
- `_strip_thinking()` 永遠套用在 `chat()` 和 `complete()` 輸出，確保 `<think>` 標籤不出現在結果中

### 9.6 命名規範

模型 family 參數統一命名 `model_family`（如 `"qwen3"`、`"gemma4"`），禁止使用 `model_type` 或 `model_id`（避免與 VRAM slot type、完整 model identifier 混淆）。複合參數使用前綴：`translate_model_family`、`summarize_model_family`。

---

## 10. API 路由結構

### 10.1 路由分類

| 前綴 | 用途 | 檔案位置 |
|------|------|---------|
| `/api/setup/` | 設定頁面（config、models、remote connections） | `routes/setup/` |
| `/api/llm/` | LLM 共用查詢（translate languages/styles/status/test） | `routes/llm.py` |
| `/api/video/` | 影片工具（subtitle、transcode、interpolate、enhance） | `routes/video/` |
| `/api/audio/` | 音訊工具（transcribe、separate、lyrics、midi） | `routes/audio/` |
| `/api/image/` | 圖片工具（upscale、ocr、remove-bg、filter） | `routes/image/` |
| `/api/document/` | 文件工具（translate、ocr、pdf-convert、split） | `routes/document/` |
| `/api/files/` | 檔案管理（upload、download） | `routes/files.py` |
| `/api/tasks/` | 任務管理（active、history） | `routes/tasks/` |

LLM 共用查詢（語言列表、翻譯風格、模型狀態）放在 `/api/llm/`，不重複掛在各 domain router 下。實際執行翻譯/OCR/摘要仍在各 domain service 的 submit endpoint。

---

## 11. 錯誤處理規範

### 11.1 Service 層

```python
# submit 方法：用 require_file 驗證；參數非法拋 ValueError
async def submit_xxx(self, file_id: str, quality: int, ...) -> str:
    file_info = self._file_service.require_file(file_id)  # FileNotFoundError_ → 404
    if not 0 <= quality <= 100:
        raise ValueError(f"quality must be 0-100, got {quality}")  # → 400

# execute 方法：讓異常自然拋出，TaskManager 會捕獲並設定 FAILED 狀態
def _execute(self, params, progress_callback):
    # 不需要 try/except，TaskManager._execute_task() 統一處理
    ...
```

異常語意：
- `FileNotFoundError_` — file_id 不存在於 FileService 登記；由 `FileService.require_file()` 自動拋出
- `ModelNotFoundError` — 模型檔案不存在（未下載）
- `ValueError` — 參數驗證失敗（如 quality 超範圍、unknown variant）
- `RemoteApiError(code, detail)` — 遠端 API 呼叫失敗
- `FFmpegError` — FFmpeg 執行失敗

### 11.2 Route 層

Routes **不寫 try/except**。全域 exception handler（`handler/error_responses.py`）自動映射：

| 異常 | HTTP 狀態 |
|---|---|
| `FileNotFoundError_` | 404 |
| `ModelNotFoundError` | 404 |
| `ValueError` | 400 |
| `RemoteApiError` | 502 |
| `FFmpegError` | 500 |
| `MediaTranXError` (基類) / 其他 | 500 |

```python
# Route 只做：呼叫 Service → 回傳
@router.post("/action")
@inject
async def do_action(request: XxxRequest, service: XxxService = Depends(...)):
    task_id = await service.submit_xxx(file_id=request.file_id, option=request.option)
    return XxxResponse(task_id=task_id)
```

### 11.3 Engine 層

Engine 方法失敗時直接拋異常，由上層 Service/TaskManager 處理。不吞異常。

---

## 12. 命名規範

### 12.1 檔案命名

| 位置 | 格式 | 範例 |
|------|------|------|
| Service | `{action}_service.py` | `compress_service.py` |
| Route | `{action}.py` | `compress.py` |
| Engine AI | `{model_name}.py` | `realesrgan.py` |

### 12.2 Class 命名

| 位置 | 格式 | 範例 |
|------|------|------|
| Service | `{Domain}{Action}Service` | `ImageCompressService` |
| Route Request | `{Action}Request` | `ImageCompressRequest` |
| Route Response | `{Action}Response` | `ImageCompressResponse` |

### 12.3 常數命名

```python
TASK_TYPE_IMAGE_COMPRESS = "image.compress"
TASK_TYPE_VIDEO_TRANSCODE = "video.transcode"
```

### 12.4 工廠函數

```python
def get_image_compress_service() -> ImageCompressService:
    ...
```

---

## 13. 新增功能 Checklist

新增一個處理功能時，按順序完成：

1. [ ] **Service**：在 `services/{domain}/` 新增 `{action}_service.py`，遵循 §4 模板
2. [ ] **DI 註冊**：在 `app/init/container.py` 的 AppContainer 註冊 Singleton
3. [ ] **Route**：在 `api/routes/{domain}/` 新增 `{action}.py`，遵循 §5 模板（DI injection）
4. [ ] **註冊 Route**：在 `api/routes/{domain}/__init__.py` include 新 router
5. [ ] **Import**：外部套件直接 top-level import
6. [ ] **日誌**：Service 初始化和任務提交/完成有 `logger.info`
7. [ ] **路徑**：所有路徑透過 `get_settings().path` 取得
8. [ ] **文件**：更新 `docs/ARCHITECTURE.md` 和本文件的相關段落

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
