# MediaTranX Architecture

> **AI-powered local multimedia processing platform** — speech recognition, translation, image processing, OCR, and media transcoding. All AI inference runs on the user's machine.

---

## 1. System Architecture

MediaTranX uses a **Client-Server** architecture — Vue 3 frontend + FastAPI backend:

```mermaid
graph TB
    subgraph Frontend["Vue 3 Frontend (port 8000)"]
        UI["ToolLayout + Workspace Composables"]
        Stores["Pinia Stores<br/>(tasks, files, settings, models)"]
        ToneJS["Tone.js MIDI Engine"]
    end

    subgraph Backend["FastAPI Backend (port 8001)"]
        Routes["API Routes"]
        Services["Services"]
        Pipeline["Pipeline<br/>(domain orchestration)"]
        Adapters["Adapters<br/>(external systems)"]
        TM["TaskManager + ProgressTracker"]
    end

    subgraph AI["AI Runtimes"]
        Llama["llama-server<br/>LLM Translation / VLM OCR"]
        PyTorch["PyTorch<br/>Super-Resolution / Face Restore / RemBG"]
        CT2["CTranslate2<br/>Whisper STT"]
        Demucs["Demucs<br/>Source Separation"]
    end

    FFmpeg["FFmpeg<br/>Media Transcoding"]
    Remote["Remote API<br/>(Ollama / OpenAI / Gemini)"]

    UI -->|"REST API + Polling"| Routes
    Routes --> Services
    Services --> Pipeline
    Services --> Adapters
    Services --> TM
    Pipeline --> Adapters
    Adapters --> Llama
    Adapters --> PyTorch
    Adapters --> CT2
    Adapters --> Demucs
    Adapters --> FFmpeg
    Adapters --> Remote
```

---

## 2. Backend Layered Architecture

```mermaid
graph LR
    R["API Routes<br/>(api/routes/)"] -->|"validate + call"| S["Services<br/>(services/)"]
    S -->|"domain orchestration"| P["Pipeline<br/>(pipeline/)"]
    S -->|"call adapter"| A["Adapters<br/>(adapters/)"]
    P --> A
    S -->|"submit tasks"| W["Workers<br/>(workers/)"]

    style R fill:#e3f2fd
    style S fill:#fff3e0
    style P fill:#f3e5f5
    style A fill:#e8f5e9
    style W fill:#fce4ec
```

**Rules:** Route → Service → (Pipeline) → Adapter. No cross-layer jumps.

```
backend/app/
├── main.py                          # FastAPI entry point
├── init/                            # Startup (DI container, configs, lifespan)
│   ├── container.py                 # DI container with _lazy() domain services
│   └── lifespan.py                  # Startup/shutdown + background warmup thread
├── api/routes/                      # Route layer (TYPE_CHECKING service imports)
│   ├── audio/, image/, video/, document/     # per-feature route files + inline DTO
│   ├── files/, llm/, health/                 # concern folders
│   ├── setup/, tasks/, agent/                # agent/ = AG-UI run + sessions
├── adapters/                        # External-system adapters (需跨層協調)
│   ├── device.py                    # GPU/CPU detection
│   ├── binary/                      # Binary subprocess wrappers
│   │   ├── ffmpeg.py, llama_server.py
│   │   └── ytdlp.py                 # yt-dlp video download
│   ├── security/                    # secret_cipher.py (API key at-rest encryption)
│   └── ai/                          # AI domain adapters
│       ├── model_manager.py         # VRAM slot + acquire coordinator
│       ├── registry.py              # Static model metadata
│       ├── tile_inference.py        # PTH tensor tile/stitch helper
│       ├── face_pipeline.py         # GFPGAN detect/align/restore orchestration
│       ├── remote/                  # HTTP provider adapters (openai/gemini/ollama, probe)
│       └── wrapper/                 # AI model lifecycle wrapper family
│           ├── base.py              # BaseWrapper / PackageWrapper / PthWrapper
│           ├── whisper.py, demucs.py, basic_pitch.py, wav2vec2.py
│           ├── bsrgan.py, realesrgan.py, swinir.py, waifu2x.py, real_cugan.py
│           ├── gfpgan.py            # face restoration (only restorer; CodeFormer removed)
│           ├── mobilesam.py, rife.py
│           └── llm.py               # LlmWrapper (wraps binary/llama_server)
├── services/                        # Business layer (service = cohesive business logic)
│   ├── audio/, image/, video/, document/     # modality feature services
│   ├── files/, llm/, setup/, tasks/, agent/  # cross-cutting services (agent/ = AG-UI)
├── pipeline/                        # Cross-service domain orchestration
│   └── translate.py, transcribe.py, ocr.py
├── utils/                           # Pure technical helpers (技術中性 + 2+ consumer)
├── workers/                         # TaskManager + ProgressTracker + media_kind
├── handler/                         # HTTP cross-cutting (exceptions + responses + middleware)
├── schemas/                         # Cross-layer domain types (TaskData, FileData)
├── db/                              # SQLModel (dao/ + models/): task_history, api_connection,
│                                    #   agent_session, agent_message, app_setting
└── main.py
```

Development specs: [BACKEND_DEVELOP_SPEC.md](BACKEND_DEVELOP_SPEC.md)

### AI Model System

```mermaid
graph TB
    subgraph Registry["Registry (adapters/ai/registry.py)"]
        FORMAT_PKG["FORMAT_PKG<br/>Whisper, Demucs"]
        FORMAT_GGUF["FORMAT_GGUF<br/>LLM: Qwen3/Gemma; VLM: Qwen3-VL/InternVL (mmproj)"]
        FORMAT_PTH["FORMAT_PTH<br/>Real-ESRGAN, GFPGAN, ..."]
        FORMAT_ONNX["FORMAT_ONNX<br/>(reserved, DirectML)"]
    end

    subgraph Manager["ModelManager (adapters/ai/model_manager.py)"]
        Slots["VRAM Slots<br/>(pth, whisper, llm, ...)"]
        Acquire["acquire(slot, model_id, variant)"]
    end

    subgraph Wrappers["Wrappers (adapters/ai/wrapper/)"]
        PKG["PackageWrapper"]
        PTH["PthWrapper<br/>+ tile_inference"]
        LLM["LlmWrapper<br/>→ binary/llama_server"]
    end

    FORMAT_PKG --> PKG
    FORMAT_PTH --> PTH
    FORMAT_GGUF --> LLM
    Manager -->|"acquire/evict"| Wrappers
```

### Remote API Providers

Support cloud models as alternatives to local models:

| Provider | Use |
|----------|-----|
| Ollama | Self-hosted LLM server |
| OpenAI | GPT translation / OCR |
| Gemini | Google AI translation / OCR |

---

## 3. Frontend Architecture

```mermaid
graph TB
    subgraph Views["Views"]
        Home["HomeView<br/>(/)"]
        Image["ImageView<br/>(/image)"]
        Audio["AudioView<br/>(/audio)"]
        Video["VideoView<br/>(/video)"]
        Doc["DocumentView<br/>(/document)"]
        Tasks["TasksView<br/>(/tasks)"]
        Settings["SettingsView<br/>(/settings)"]
    end

    subgraph Composables["Shared Composables"]
        WS["useMediaCollection"]
        Submit["useSubmitTask"]
        Multi["useMultiSubmit"]
    end

    subgraph Components["Shared Components"]
        TL["ToolLayout<br/>(3-column)"]
        FS["AppFilmstrip<br/>(multi-file)"]
        CS["ComparisonSlider"]
    end

    Views --> Composables
    Views --> Components
```

### Pinia Stores

| Store | Description |
|-------|-------------|
| `tasks` | Task state (`Map<taskId, Task>`) + polling sync |
| `files` | File upload / local registration |
| `settings` | User preferences (theme, locale, paths) |
| `models` | Local AI model state |
| `remoteModels` | Cloud API model lists |
| `agent` / `agentSettings` | Agent chat bubble: run state, sessions, model/connection choice |
| `results` | Results drawer (task outputs) |
| `videoDownload` | yt-dlp download queue |

### Shared Framework

- **ToolLayout**: 3-column layout (sidebar + preview + settings), resizable
- **AppFilmstrip**: Multi-file management bar, Shift+drag selection, Ctrl+click
- **useMediaCollection**: Multi-file state composable, shared across all tools
- **useSubmitTask**: Task submission (POST → store → toast)
- **ComparisonSlider**: Before/after image comparison slider

Development specs: [FRONTEND_DEVELOP_SPEC.md](FRONTEND_DEVELOP_SPEC.md)

---

## 4. Task Lifecycle

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant R as Route
    participant S as Service
    participant TM as TaskManager
    participant A as Adapter

    FE->>R: POST /api/{domain}/{action}
    R->>S: submit_xxx(file_id, params)
    S->>TM: submit(task_type, params)
    TM-->>FE: task_id
    FE->>FE: Add to TaskStore, start polling

    loop Every 1s
        FE->>R: GET /api/tasks/
        R-->>FE: task status + progress
    end

    TM->>S: _handle_task(params, progress_callback)
    S->>A: AI inference / FFmpeg (via mm.acquire)
    A-->>S: result
    S-->>TM: {output_file_id, output_filename}
    TM-->>FE: status=completed + result

    FE->>FE: Update preview / enable download
```

---

## 5. Data Paths

All paths managed via `PathSettings` (a pydantic `BaseModel`; `root`/`temp` are top-level, the rest are `computed_field`s derived from `root`; Electron overrides via `MEDIATRANX_PATH__*` env vars):

| Directory | Default (dev) | Production |
|-----------|---------------|------------|
| Models | `backend/models/` | `%APPDATA%/MediaTranX/models/` |
| Venv | `backend/.venv/` | `%APPDATA%/MediaTranX/.venv/` |
| Bin | `backend/bin/` | `%LOCALAPPDATA%/MediaTranX/resources/bin/` |
| Temp | `backend/temp/` | `%APPDATA%/MediaTranX/temp/` |
| Logs | `backend/logs/` | `%APPDATA%/MediaTranX/logs/` |
| DB | `backend/mediatranx.db` | `%APPDATA%/MediaTranX/mediatranx.db` |

---

## 6. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| **System & Setup** | | |
| GET | `/api/health` | Health check |
| GET | `/api/health/deep` | Deep health check |
| GET | `/api/device` | GPU/CPU device info |
| POST | `/api/device/refresh` | Refresh device state |
| GET | `/api/setup/status` | AI environment status |
| POST | `/api/setup/initialize` | Start AI environment installation |
| GET/POST | `/api/setup/config` | App configuration |
| GET | `/api/setup/models` | Model list |
| POST | `/api/setup/models/download` | Download model |
| POST | `/api/setup/models/remove` | Remove model |
| GET/POST | `/api/setup/remote/connections` | Cloud API connection management |
| GET | `/api/setup/remote/models` | Cloud model list |
| **Files** | | |
| POST | `/api/files/upload` | Upload file |
| POST | `/api/files/register` | Register local file (Electron) |
| GET | `/api/files/{id}/download` | Download file |
| POST | `/api/files/cleanup` | Cleanup temp files |
| **Tasks** | | |
| GET | `/api/tasks/` | Active tasks (status + progress, polled) |
| GET | `/api/tasks/{id}` | Single task status (progress included in response) |
| POST | `/api/tasks/{id}/cancel` | Cancel task |
| DELETE | `/api/tasks/{id}` | Dismiss active task |
| GET | `/api/tasks/history` | Task history |
| **Agent** (AG-UI) | | |
| POST | `/api/agent/run` | Run agent turn (SSE stream of AG-UI events) |
| GET | `/api/agent/sessions` | List chat sessions |
| GET | `/api/agent/sessions/{id}/messages` | Load session messages |
| POST | `/api/agent/sessions/{id}/messages` | Persist message |
| DELETE | `/api/agent/sessions/{id}` | Delete session |
| **LLM** | | |
| GET | `/api/llm/translate/languages` | Supported translation languages |
| GET | `/api/llm/translate/styles` | Supported translation styles |
| GET | `/api/llm/translate/status` | Translation model status |
| POST | `/api/llm/chat` | Direct LLM chat (test) |
| **Video** | | |
| GET | `/api/video/info/{file_id}` | Media info |
| POST | `/api/video/transcode` | Transcode |
| POST | `/api/video/cut` | Cut |
| POST | `/api/video/extract-audio` | Extract audio track |
| POST | `/api/video/subtitle/generate` | Subtitle extraction (Whisper) |
| POST | `/api/video/interpolate` | Frame interpolation (RIFE) |
| POST | `/api/video/enhance` | Video enhancement (Real-ESRGAN) |
| POST | `/api/video/crop` | Crop video frame (spatial) |
| POST | `/api/video/summary` | Video summary (subtitle → LLM markdown + key frames, ZIP) |
| **Audio** | | |
| GET | `/api/audio/info/{file_id}` | Audio info |
| POST | `/api/audio/transcode` | Transcode |
| POST | `/api/audio/cut` | Cut |
| POST | `/api/audio/volume` | Volume adjust |
| POST | `/api/audio/transcribe` | Speech-to-text |
| POST | `/api/audio/separate` | Source separation (Demucs) |
| POST | `/api/audio/lyrics` | Lyrics extraction |
| GET/POST | `/api/audio/midi/*` | MIDI editing & export |
| **Image** | | |
| GET | `/api/image/info/{file_id}` | Image info |
| POST | `/api/image/convert` | Format conversion |
| POST | `/api/image/upscale` | Super-resolution |
| POST | `/api/image/remove-bg` | Background removal |
| POST | `/api/image/remove-object` | Object removal (SAM + LaMa) |
| POST | `/api/image/filter` | Filters |
| POST | `/api/image/crop` | Crop |
| POST | `/api/image/ocr` | OCR (VLM) |
| **Document** | | |
| POST | `/api/document/ocr` | OCR (VLM) |
| POST | `/api/document/translate` | Translation |
| POST | `/api/document/split` | Split |
| POST | `/api/document/pdf-convert` | PDF conversion |

---

## 7. Development

### Requirements

- Node.js 18+
- Python 3.12 (managed via [uv](https://docs.astral.sh/uv/))
- NVIDIA GPU + CUDA (recommended 6GB+ VRAM), CPU also supported

### Start

```bash
# Frontend (Vite default port 5173; Electron injects VITE_PORT=8000 at runtime)
cd frontend && npm install && npm run dev

# Backend (port 8001)
cd backend && uv sync && uv run python -m app.main --mode dev --port 8001
```

### AI Models

After launch, download models from **Settings > AI Models**.
