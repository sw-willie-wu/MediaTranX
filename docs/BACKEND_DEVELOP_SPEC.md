# 後端開發規範

> 所有後端新增與修改**必須**遵循此文件。違反規範的程式碼不應合併。

---

## 1. 後端架構與命名規範

> 本章定義 `app/` 下各資料夾邊界、命名規範、層級依賴。新增/修改 code 前必須對照此章確認目標位置。

### 1.1 目錄結構

```
app/
├── main.py                             # FastAPI app entry
├── api/                                # HTTP routing + inline DTO
│   └── routes/
│       ├── audio/, image/, video/, document/
│       ├── files/, llm/, health/
│       └── setup/, tasks/
├── adapters/                           # 外部系統 adapter（需跨層協調）
│   ├── device.py                       # 硬體/OS 查詢
│   ├── binary/                         # binary subprocess wrapper
│   │   ├── ffmpeg.py
│   │   └── llama_server.py
│   └── ai/                             # AI domain adapter
│       ├── model_manager.py            # VRAM slot + acquire 協調（單例）
│       ├── registry.py                 # 靜態 model metadata
│       ├── tile_inference.py           # PTH tensor tile/stitch helper
│       ├── remote/                     # HTTP provider adapter
│       │   ├── base.py
│       │   └── openai.py, gemini.py, ollama.py
│       └── wrapper/                    # AI model lifecycle wrapper 家族
│           ├── base.py                 # BaseWrapper / PackageWrapper / PthWrapper
│           ├── whisper.py, demucs.py, basic_pitch.py, wav2vec2.py
│           ├── bsrgan.py, realesrgan.py, swinir.py, waifu2x.py, real_cugan.py
│           ├── codeformer.py, gfpgan.py
│           ├── mobilesam.py, rife.py
│           └── llm.py                  # 包 binary/llama_server
├── services/                           # DI business services
│   ├── audio/, image/, video/, document/    # modality feature services
│   └── files/, llm/, setup/, tasks/         # cross-cutting services
├── pipeline/                           # 跨 service domain orchestration
│   └── translate.py, transcribe.py, ocr.py
├── utils/                              # 純技術 helper（技術中性 + 2+ 終端 consumer）
├── workers/                            # async task infrastructure
│   └── task_manager.py, progress_tracker.py, media_kind.py
├── handler/                            # HTTP 層橫切 plumbing
│   └── exceptions.py, error_responses.py, middleware.py
├── schemas/                            # 跨層共用 domain model
│   └── file.py, task.py
├── init/                               # 應用 bootstrap
│   └── container.py, configs/, logging_config.py, lifespan.py, compat.py, setup.py
└── db/                                 # 資料持久層（SQLModel）
    └── database.py, models/, dao/
```

### 1.2 各層責任邊界

#### 1.2.1 `api/` — HTTP routing

**責任**：FastAPI endpoint、request/response validation、呼叫 service。不含業務邏輯。

- 每個 concern 一個 folder（即使只 1 feature，保結構一致）
- Folder 內每檔 = 一個 feature；Pydantic BaseModel inline 定義在該 feature 檔案頂部
- **拆分原則**：
  - **拆**：不同 feature / resource 的 endpoint 分檔（e.g. `files/upload.py` vs `files/download.py`）
  - **不拆**：同 feature 的多個 endpoint（主任務 + 查詢 helper、同 resource CRUD）放一起（e.g. `audio/transcribe.py` 含 POST `/transcribe` + GET `/transcribe/languages` + GET `/transcribe/sizes`）

#### 1.2.2 `schemas/` — 跨層共用 domain model

**責任**：services 與 api 都會接觸的資料 shape。純 Python dataclass / enum，避免 services/workers 反向依賴 api 層。

- 典型內容：`FileData`、`TaskState`、`TaskStatus` enum
- **不放**：endpoint 專用 request/response DTO（inline 在 route 檔）

API 層的 Pydantic models（`TaskResponse`、`FileInfo`）在對應 route 檔中定義，透過 `from_task_data()` / `from_file_data()` 由 schemas/ 的 domain model 轉換。

#### 1.2.3 `services/` — DI 業務邏輯

**責任**：DI singleton，每個 service = 一個內聚的業務邏輯。Endpoint 數量（0/1/N）不是分類依據。

三類表現形式（全部走同一條規則）：
- 對應 1 個 endpoint（e.g. `image/upscale_service`）
- 對應多個 endpoint（e.g. `files/file_service` — 檔案管理多面向）
- 0 個 endpoint，internal-only（e.g. `llm/chat_service` — 被其他 service 透過建構子注入）

**單檔 vs subpackage 門檻**：
- 單檔 `<feature>_service.py`：業務邏輯 < ~300 行
- 子包 `<feature>_service/`：超過 300 行，或有明確不同主題的 helpers

**Subpackage 內部組織**：

```
services/video/summary_service/
├── __init__.py              # re-export VideoSummaryService
├── service.py               # 業務主軸（submit_ / _execute / 和其他 service 互動）
├── parse.py                 # LLM 輸入輸出 plumbing（主題命名）
├── markdown.py              # 最終 doc 組裝（主題命名）
└── frame_picker.py          # 場景幀挑選（主題命名）
```

- `service.py` = 業務類別本體
- 其他檔 = **以關注點命名**
- `__init__.py` 只 re-export class，不放邏輯

#### 1.2.4 `pipeline/` — 跨 service domain orchestration

**責任**：跨 service 共用 + 具 domain 概念的 inference 編排。

**判準（兩者皆需）**：
- 2+ service 直接消費
- 涉及 domain orchestration（「翻譯」「OCR」「轉錄」之類概念）

現有 3 檔：
- `translate.py` — SRT batch translate（transcribe / lyrics / subtitle / document_translate 4 service 共用）
- `transcribe.py` — demucs → whisper → align 編排
- `ocr.py` — VLM single-image OCR（image_ocr / doc_ocr 2 service 共用）

只有 1 service consumer 的 helper 不是 pipeline，放進該 service 的 subpackage。

#### 1.2.5 `adapters/` — 外部系統 adapter

**責任**：包「不是我們寫的東西」—— binary、第三方 Python 套件、遠端 HTTP API、OS/硬體資源。**放這層的判準：需要跨層協調**（統一 VRAM slot、binary 路徑、硬體 cache）；只在一個 consumer 用且不涉協調的不是 adapter 而是 service-local helper。

分三塊：

| 塊 | 內容 |
|---|---|
| `device.py` | 硬體查詢（CUDA 偵測、compute type 選擇） |
| `binary/` | binary subprocess wrapper：`ffmpeg.py`、`llama_server.py` |
| `ai/` | AI domain adapter（見下） |

**`adapters/ai/` 內部**：

| 檔/包 | 責任 |
|---|---|
| `model_manager.py` | 單例；VRAM slot lock、evict、lazy runtime factory、`mm.acquire(slot, model_id, variant)` 公開入口 |
| `registry.py` | 靜態 model metadata（name / size / VRAM / repo_id / file format / slot） |
| `tile_inference.py` | PTH 家族共用 tensor tile/stitch helper |
| `remote/` | HTTP provider adapter（openai、gemini、ollama；`base.py` 定抽象） |
| `wrapper/` | AI model lifecycle wrapper 家族 |

**`wrapper/` 只放 wrapper 本身 + 基類**：
- `base.py` — `BaseWrapper` / `PackageWrapper` / `PthWrapper`（lifecycle 基類）
- `whisper.py` / `bsrgan.py` / ... / `llm.py` — 具體 wrapper 實作
- 不放非 wrapper 的 helpers（避免命名誤導）

**`tile_inference.py` 為什麼在 `ai/` 頂層而不是 `wrapper/` 內？**
放 `wrapper/` 內會被誤認是某個 model wrapper。`tile_inference` 不是 wrapper，是 wrapper 家族共用的 tensor helper，放 ai/ 頂層（和 `model_manager` / `registry` 同層）語義清楚。

**`llama_server` 為什麼拆成 `binary/llama_server.py` + `ai/wrapper/llm.py`？**
- `binary/llama_server.py` = 純 binary adapter（subprocess + HTTP），不知道 model registry / mmproj / VRAM slot
- `ai/wrapper/llm.py`（`LlmWrapper`）= AI-domain lifecycle；繼承 wrapper base class，組合 `LlamaServer` 做為實作細節，知道 registry + load/unload 語義
- 類比 ffmpeg：也是 binary subprocess wrapper，但不綁特定 domain，獨立在 `binary/`

**Remote Provider 介面**（`adapters/ai/remote/`）：
- 每個 Provider 實作 `connect()` / `list_models()` / `chat()`
- `chat()` 支援 vision messages（各 provider 格式不同，內部轉換）
- Model capabilities 從 API 偵測（Ollama `/api/show`、OpenAI 已知表、Gemini `supportedGenerationMethods`）
- 錯誤統一拋 `RemoteApiError(code, detail)`

#### 1.2.6 `utils/` — 純技術 helper

**責任**：可被上層自由 import 的純函數 / 資料處理 / 技術 boilerplate。**無 DI、無 container、無 domain state**。

**收錄條件（三者皆需）**：
1. 純資料/技術處理，無業務邏輯
2. **技術中性**（通用 format / algorithm，與特定 domain 解耦）
3. 被 2+ 終端 consumer 使用（transitive 計算）

**Transitive consumer 計算**：若 `utils/A.py` 被 `utils/B.py` import，A 的 consumer 數 = B 的終端 consumer + A 的直接終端 consumer。防止「A 只服務 B、B 只服務 1 個 service」的 loophole。

**utils 內部可互相 import**，單向、無循環；高層 utils 組合低層 utils 是合法 composition。

**不符合收錄條件時**：
- 符合 (1)(3) 但高度 domain-specific、consumer 全在一個家族（如 PTH tensor tile）→ 放家族協調層（如 `adapters/ai/tile_inference.py`）
- 符合 (1)(2) 但只 1 consumer → 放該 consumer 的 service subpackage
- 只 1 consumer 的 workers helper → 放 `workers/`

#### 1.2.7 `workers/` — async task infrastructure

**責任**：任務排程與進度回報基礎設施，非 domain-specific。

- `task_manager.py` — TaskManager（排程、狀態、錯誤捕獲）
- `progress_tracker.py` — 進度查詢
- `media_kind.py` — 檔案類型推斷（task_manager 用於 dispatch）

#### 1.2.8 `handler/` — HTTP 層橫切 plumbing

**責任**：攔截 request/response flow 的橫切關注，不屬特定 route。

- `exceptions.py` — 自訂 exception 階層（services 拋、api 層攔）
- `error_responses.py` — `ErrorResponse` DTO + exception → HTTP 映射
- `middleware.py` — FastAPI middleware

**自訂例外階層**（`handler/exceptions.py`）：

```
MediaTranXError
├── ModelNotFoundError      # 模型未找到
├── ModelLoadError          # 模型載入失敗
├── InferenceError          # AI 推論錯誤
├── TaskError               # 任務執行錯誤
├── FileNotFoundError_      # 檔案未找到
├── ConfigError             # 設定錯誤
├── FFmpegError             # FFmpeg 執行失敗
├── TaskCancelledError      # 任務被使用者取消
└── RemoteApiError          # 雲端 API 錯誤（帶 error code 供前端 i18n）
```

`RemoteApiError` 帶 `code` 欄位（`gpu_oom`、`quota_exceeded` 等），TaskManager 存入 `error_code`，前端以 `t('tasks.errors.{code}')` 翻譯。

#### 1.2.9 `init/` — 應用 bootstrap

- `configs/` — `AppSettings` container + per-concern modules（`paths.py`、`db.py`、`server.py`）
- `logging_config.py` — logging handler + format setup
- `container.py` — DI `AppContainer` 定義 + `init_container()`
- `lifespan.py` — FastAPI startup/shutdown hook（含 background warmup）
- `compat.py`、`setup.py` — DLL 注入、sys.path 準備

#### 1.2.10 `db/` — 資料持久層

使用 SQLModel（Pydantic + SQLAlchemy），SQLite 儲存：

- `db/database.py` — Engine 建立、WAL 模式、自動 migration
- `db/models/` — ORM models：`ApiConnection`、`TaskHistory`
- `db/dao/` — DAO pattern 封裝 CRUD，Service 不直接寫 SQL

```python
from app.db.dao.api_connection_dao import ApiConnectionDAO
dao = ApiConnectionDAO()
conn = dao.create(provider="ollama", name="Local", endpoint="http://localhost:11434")
```

### 1.3 命名規範

#### 1.3.1 Service 檔/包

| 形態 | 命名 | 範例 |
|---|---|---|
| 單檔 | `<feature>_service.py` | `cut_service.py` |
| 子包 | `<feature>_service/` | `summary_service/` |

兩者對外 import path 一致：`from app.services.<domain>.<feature>_service import <Feature>Service`。

#### 1.3.2 Class 命名

| 角色 | 格式 | 範例 |
|---|---|---|
| Service | `{Domain}{Feature}Service` 或 `{Feature}Service` | `ImageUpscaleService` |
| Wrapper | `{Model}Wrapper` | `WhisperWrapper`、`BSRGANWrapper` |
| Request/Response | `{Feature}Request` / `{Feature}Response` | `ImageUpscaleRequest` |
| 例外 | 依業務含義 | `FileNotFoundError_`、`RemoteApiError` |

#### 1.3.3 Subpackage 內部檔名

- **以關注點命名**（反映「做什麼」）
- **禁用** `helpers.py` / `utils.py` / `common.py`（role-based 無資訊量）
- 範例：`summary_service/` 內 `parse.py`（LLM I/O）、`markdown.py`（doc 組裝）、`frame_picker.py`（場景幀選）

#### 1.3.4 `_` prefix 規則

`_` 只在**外部真正不該 read/write** 才加。預設不加。

| 情境 | 加 `_` | 理由 |
|---|---|---|
| Class 內部 state（mutation 有 invariant） | ✓ | `_lock`、`_model`、`_runtimes` |
| Module-private constant（防外部 `from x import _Y`） | ✓ | `_MAX_CHARS_PER_LINE`、`_PAUSE_THRESHOLD_S` |
| Subclass override hook（Python template method） | ✓ | `_load_impl`、`_unload_impl`、`_resolve_model_path` |
| Subpackage 內部檔案 | ✗ | package boundary 即 encapsulation（`frame_picker.py`） |
| Subpackage 內部 module 裡的 function | ✗ | 同上 |
| Instance field 外部會合理讀 | ✗ | 直接 public（`self.slot`） |
| Cross-class contract method | ✗ | 該 public 就 public；`BaseWrapper.load/unload` 被 `ModelManager` 跨 class call，不裝私有 |

#### 1.3.5 常數命名

```python
TASK_TYPE_IMAGE_UPSCALE = "image.upscale"
TASK_TYPE_VIDEO_TRANSCODE = "video.transcode"
```

### 1.4 層級依賴規則

導入方向：

```
  api ──► services ──► pipeline ──► adapters ──► utils
   │         │            │            │            ▲
   │         └── workers ─┘            ▼            │
   │                              (pure helpers)    │
   ▼                                                │
  handler, schemas, init (橫切 / bootstrap) ────────┘
```

**允許 import**：

| 層 | 可 import |
|---|---|
| `api/` | `services/`（via DI）、`schemas/`、`handler/` |
| `services/` | `pipeline/`、`adapters/`、`utils/`、`workers/`（via DI）、`schemas/`、`db/` |
| `pipeline/` | `adapters/`、`utils/`、`schemas/` |
| `adapters/` | `utils/`、stdlib、第三方 |
| `utils/` | stdlib、第三方、`utils/`（單向無循環）、`schemas/` |
| `workers/` | `utils/`、`schemas/`、`services/`（via DI） |
| `handler/` | `schemas/` |
| `init/` | everything（bootstrap 角色） |

**禁止**：
- Route 直接 import `adapters/`（須經 service）
- Service 直接 import 其他 service 模組（須透過建構子注入）
- `pipeline/` import `services/`（反向違規）
- `utils/` import `services/` / `adapters/` / `pipeline/` / `workers/`
- `workers/` import `api/`
- `adapters/` 含業務邏輯（不知「壓縮」「轉檔」概念，只提供技術能力）

**TYPE_CHECKING 例外**：route 檔案的 domain service import 放 `if TYPE_CHECKING:` 內（見 §3 Cold Start）。

### 1.5 舊命名對照（遺留項）

> **Status: 2026-04-19 — all entries completed during refactor waves A/B/C/D. Retained as historical mapping.**

本次規範對現有程式碼的 rename / 搬家清單，實際執行透過重構 wave 分批推進。spec 先行定義目標狀態，code 尚未全部遷移：

| 舊 | 新 |
|---|---|
| `app/engine/` | `app/adapters/` |
| `app/engine/ai/runtime/{base,package,pth}.py` | `app/adapters/ai/wrapper/base.py`（合併） |
| `app/engine/ai/{audio,image,video}/` | `app/adapters/ai/wrapper/`（扁平化） |
| `app/engine/ai/remote/` | `app/adapters/ai/remote/` |
| `app/engine/ffmpeg.py` | `app/adapters/binary/ffmpeg.py` |
| `app/engine/ai/runtime/llama_server.py` | 拆：`app/adapters/binary/llama_server.py` + `app/adapters/ai/wrapper/llm.py` |
| `app/engine/device.py` | `app/adapters/device.py` |
| `app/engine/video/scene_detect.py` | `app/services/video/summary_service/scene_detect.py`（1 consumer） |
| `BaseRuntime` / `PackageRuntime` / `PthRuntime` | `BaseWrapper` / `PackageWrapper` / `PthWrapper` |
| `app/services/video/summary/` | `app/services/video/summary_service/`（補 `_service` 後綴） |
| `app/services/video/_frame_picker.py` | `app/services/video/summary_service/frame_picker.py`（搬入 + 去 `_`） |
| `app/services/document/translate_service.py` | `app/services/document/translate_service/service.py` |
| `app/services/document/translate_text.py` | `app/services/document/translate_service/text.py` |
| `app/utils/summarize.py` | `app/services/audio/transcribe_service/summarize.py`（1 consumer） |
| `app/utils/text_chunking.py` | 留 utils/（2 subpackage consumer） |
| `app/utils/media_kind.py` | `app/workers/media_kind.py`（1 consumer） |
| `app/utils/midi.py` | 改名 `app/utils/midi_io.py`（shared util；`midi_to_json` + `json_to_midi` 兩 consumer：`audio_midi_service` + `separate_service/midi_compose.py`）。`separate_service/midi_compose.py` 只含 `merge_tracks_to_midi` + `transcribe_drums`。[^midi-c4] |
| `ModelManager` 舊 `acquire(slot, required_vram_mb)` | 改 `_acquire_lock` 私有；公開 API 為 `acquire(slot, model_id, variant, on_progress)` |

[^midi-c4]: C4 deviation — `merge_tracks_to_midi` 呼叫 `json_to_midi`，所以把 I/O 函數留在 shared util（符合 §1.2.6 的 2+ consumer 判準）比複製一份到 service-local 乾淨。只把真正 composition-specific 的函數搬進 service subpackage。

命名大原則：
1. **語義誠實**：`engine/` 太含糊改 `adapters/`；`runtime/` 除 LLM 外都只做 lifecycle 不做推論，改 `wrapper/`
2. **按 domain 分區**：`ai/` 不管執行模型都收（in-process / binary / remote）；`binary/` 收跨 domain 的 binary adapter
3. **Consumer 驅動 scope**：共用工具留 utils/、單一 consumer 進 service subpackage、家族內部共用留家族層

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

### 3.1 Service / Adapter 檔案

AI 套件（PIL、numpy、torch 等）在 Electron 啟動時由 `uv sync` 安裝完成，可直接 top-level import。這些檔案在容器首次 resolve 時才被載入，不影響啟動速度。

```python
# ✓ 正確：Service / Adapter 內直接 top-level import
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

### 3.4 Adapter `__init__.py`

Adapter 的 `__init__.py` **不可**在 module level 直接 re-export wrapper class（會觸發整條 import chain）。消費者直接從具體模組 import。工廠函數內使用 lazy import：

```python
# ✗ 禁止：__init__.py 中 eagerly re-export
from .realesrgan import RealESRGANWrapper   # 觸發 torch import chain

# ✓ 正確：消費者直接 import 具體模組
from app.adapters.ai.wrapper.realesrgan import RealESRGANWrapper

# ✓ 正確：工廠函數使用 lazy import
def get_upscaler(model_id: str):
    if model_id == "realesrgan":
        from app.adapters.ai.wrapper.realesrgan import RealESRGANWrapper
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

路徑由 Electron 透過 `MEDIATRANX_*` 環境變數注入，Python 的 `PathSettings` 讀取。Dev 模式下使用預設值（`backend/` 子目錄）。

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
adapters/ai/registry.py          → 每個模型 family 的 inference config（per-task 採樣參數 + prompt builder）
adapters/ai/inference_config.py  → get_inference_config()、get_remote_inference_config()（registry-backed 查詢）
utils/inference.py               → calc_max_tokens()、calc_batch_size()、estimate_tokens()（純計算 helper）
utils/prompts.py                 → get_prompt_builder()（per-model prompt builder dispatch）
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
from app.adapters.ai.inference_config import get_inference_config
from app.utils.inference import calc_max_tokens, estimate_tokens
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
| `/api/llm/` | LLM 共用查詢（translate languages/styles/status/test） | `routes/llm/` |
| `/api/video/` | 影片工具（subtitle、transcode、interpolate、enhance） | `routes/video/` |
| `/api/audio/` | 音訊工具（transcribe、separate、lyrics、midi） | `routes/audio/` |
| `/api/image/` | 圖片工具（upscale、ocr、remove-bg、filter） | `routes/image/` |
| `/api/document/` | 文件工具（translate、ocr、pdf-convert、split） | `routes/document/` |
| `/api/files/` | 檔案管理（upload、download、metadata） | `routes/files/` |
| `/api/tasks/` | 任務管理（active、history） | `routes/tasks/` |
| `/api/health/` | 健康檢查與裝置狀態 | `routes/health/` |

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

### 11.3 Adapter 層

Adapter 方法失敗時直接拋異常，由上層 Service/TaskManager 處理。不吞異常。

---

## 12. 新增功能 Checklist

新增一個處理功能時，按順序完成：

1. [ ] **Service**：在 `services/{domain}/` 新增 `{feature}_service.py`（或升子包 `{feature}_service/`），遵循 §4 模板
2. [ ] **DI 註冊**：在 `app/init/container.py` 的 AppContainer 註冊 Singleton
3. [ ] **Route**：在 `api/routes/{domain}/` 新增 `{feature}.py`（concern folder 內），遵循 §5 模板
4. [ ] **註冊 Route**：在 `api/routes/{domain}/__init__.py` include 新 router
5. [ ] **Import**：外部套件直接 top-level import
6. [ ] **日誌**：Service 初始化和任務提交/完成有 `logger.info`
7. [ ] **路徑**：所有路徑透過 `get_settings().path` 取得
8. [ ] **命名**：遵循 §1.3（service 後綴、subpackage 內主題命名、`_` prefix 規則）
9. [ ] **文件**：更新 `docs/ARCHITECTURE.md` 和本文件的相關段落

### 新增本地 AI 模型

1. [ ] 在 `adapters/ai/registry.py` 新增模型定義
2. [ ] 在 `adapters/ai/wrapper/` 新增 `{model}.py`，繼承對應基類（`BaseWrapper` / `PackageWrapper` / `PthWrapper`）
   - Image PTH 模型：`PthWrapper`（torch state_dict 載入，VRAM-aware tile inference via `tile_inference.py`）
   - Python 套件模型：`PackageWrapper`（第三方套件自帶載入，如 faster-whisper / demucs）
   - LLM (GGUF)：繼承合適基類；包 `adapters/binary/llama_server.py`
3. [ ] 在 `container.py` 加 `_lazy()` Singleton provider；於 `init_container()` 呼叫 `mm.register_runtime_provider(slot, provider)`（非 dispatcher slot）或 `mm.register_dispatcher(slot, dispatcher)`（如 upscale/face_restore）
4. [ ] 在 Service 的 `_execute` 方法中透過 `mm.acquire(slot, model_id, variant)` 呼叫

### 新增遠端 API Provider

1. [ ] 在 `adapters/ai/remote/` 新增 `{provider}.py`，繼承 `RemoteProvider`
2. [ ] 實作 `connect()`、`list_models()`、`chat()`
3. [ ] 在 `remote/__init__.py` 匯出
4. [ ] 在 `services/setup/remote_service.py` 的 `_get_provider()` 加入分支
5. [ ] 前端 `ModelDownloadManager.vue` 的 `providerOptions` 加入選項
