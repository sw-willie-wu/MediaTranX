# 後端目錄重組計畫

## Context

兩個重組任務：
1. `main.py` 的 bootstrap 邏輯抽到 `app/init/`
2. `engine/ai/` 按功能重新分類 + `gif_utils` 移到 `app/utils/`

## 動工順序

先做 ai/ 重組（影響範圍大，先處理），再做 init/（獨立，不影響其他）。

---

### Step 1: 建立新目錄結構（空殼）

```
app/utils/__init__.py
app/init/__init__.py
app/init/dll_injection.py
app/init/logging_config.py
app/init/compat.py
app/engine/ai/runtime/__init__.py
app/engine/ai/image/__init__.py
app/engine/ai/audio/__init__.py
app/engine/ai/remote/__init__.py
```

### Step 2: 移動 runtime 基礎類別

```
base/runtime.py           → runtime/base.py
base/package_runtime.py   → runtime/package.py
base/pth_runtime.py       → runtime/pth.py
base/gguf_runtime.py      → runtime/gguf.py
base/llama_server_runtime.py → runtime/llama_server.py
base/translate.py         → llama/translate.py（不是 runtime）
```

- 更新 `runtime/__init__.py` export
- 全域更新 import：`from app.engine.ai.base.xxx import` → `from app.engine.ai.runtime.xxx import`
- 刪除 `base/` 目錄

### Step 3: 移動 image 模型

```
pth/realesrgan.py    → image/realesrgan.py
pth/real_cugan.py    → image/real_cugan.py
pth/swinir.py        → image/swinir.py
pth/bsrgan.py        → image/bsrgan.py
pth/waifu2x.py       → image/waifu2x.py
pth/codeformer.py    → image/codeformer.py
pth/gfpgan.py        → image/gfpgan.py
```

- 加上 mobilesam（如果有獨立檔案的話）
- 更新 import
- 刪除 `pth/` 目錄

### Step 4: 移動 audio 模型

```
pkg/whisper.py    → audio/whisper.py
pkg/wav2vec2.py   → audio/wav2vec2.py
pkg/demucs.py     → audio/demucs.py
```

- 更新 import
- 刪除 `pkg/` 目錄

### Step 5: llama/ 保持不動

`llama/` 已經在正確位置，只需要把 `base/translate.py` 移進來。

### Step 6: 移動 gif_utils

```
engine/gif_utils.py → app/utils/gif_utils.py
```

- 更新 import（`services/image/filter_service.py`、`services/image/remove_bg_service.py`）

### Step 7: 建立 app/init/ bootstrap

```
main.py 的以下邏輯搬到 app/init/：
- dll_injection.py：sys.path + add_dll_directory + CUDA DLL
- logging_config.py：日誌配置
- compat.py：torchvision 相容層
- __init__.py：bootstrap() 按順序呼叫
```

main.py 瘦身為 ~15 行。

### Step 8: 驗證

1. `grep -rn "from app.engine.ai.base" app/` → 0 結果
2. `grep -rn "from app.engine.ai.pth" app/` → 0 結果
3. `grep -rn "from app.engine.ai.pkg" app/` → 0 結果
4. `grep -rn "from app.engine.gif_utils" app/` → 0 結果
5. 重啟 app，所有功能正常

---

## 最終結構

```
app/
├── init/                    # 啟動 bootstrap
│   ├── __init__.py          # bootstrap()
│   ├── dll_injection.py
│   ├── logging_config.py
│   └── compat.py
├── utils/                   # 通用工具
│   └── gif_utils.py
├── engine/
│   ├── paths.py
│   ├── device.py
│   ├── database.py
│   ├── ffmpeg.py
│   └── ai/
│       ├── registry.py
│       ├── model_manager.py
│       ├── runtime/         # 抽象基底
│       │   ├── base.py
│       │   ├── package.py
│       │   ├── pth.py
│       │   ├── gguf.py
│       │   └── llama_server.py
│       ├── image/           # 影像 AI
│       │   ├── realesrgan.py
│       │   ├── swinir.py
│       │   ├── bsrgan.py
│       │   ├── real_cugan.py
│       │   ├── waifu2x.py
│       │   ├── codeformer.py
│       │   └── gfpgan.py
│       ├── audio/           # 語音 AI
│       │   ├── whisper.py
│       │   ├── wav2vec2.py
│       │   └── demucs.py
│       ├── llama/           # LLM（本地 llama-server）
│       │   ├── gemma.py
│       │   ├── qwen3.py
│       │   ├── vlm.py
│       │   └── translate.py
│       └── remote/          # 外部 API（未來）
│           └── __init__.py
├── api/
├── services/
├── workers/
├── models/
└── exceptions.py
```

## Import 更新範圍

| 舊 import | 新 import | 影響檔案數（估） |
|-----------|-----------|------------|
| `app.engine.ai.base.runtime` | `app.engine.ai.runtime.base` | ~5 |
| `app.engine.ai.base.package_runtime` | `app.engine.ai.runtime.package` | ~3 |
| `app.engine.ai.base.pth_runtime` | `app.engine.ai.runtime.pth` | ~8 |
| `app.engine.ai.base.translate` | `app.engine.ai.llama.translate` | ~5 |
| `app.engine.ai.pth.*` | `app.engine.ai.image.*` | ~8 |
| `app.engine.ai.pkg.*` | `app.engine.ai.audio.*` | ~6 |
| `app.engine.gif_utils` | `app.utils.gif_utils` | ~2 |
