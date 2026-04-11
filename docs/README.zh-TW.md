# MediaTranX

[![GitHub release](https://img.shields.io/github/v/release/sw-willie-wu/MediaTranX)](https://github.com/sw-willie-wu/MediaTranX/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)](https://github.com/sw-willie-wu/MediaTranX/releases)
[![GitHub stars](https://img.shields.io/github/stars/sw-willie-wu/MediaTranX)](https://github.com/sw-willie-wu/MediaTranX/stargazers)

[![Electron](https://img.shields.io/badge/Electron-34-47848F?logo=electron&logoColor=white)](https://www.electronjs.org/)
[![Vue 3](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)

**基於 AI 的本地多媒體處理工具** — 語音辨識、翻譯、超解析、OCR 與格式轉換。所有 AI 推理在你的電腦上本地執行。

[English](../README.md)

[![Demo 影片](https://img.youtube.com/vi/r5vivvL1Nds/maxresdefault.jpg)](https://youtu.be/r5vivvL1Nds)

---

## 功能

### 圖片工具
- 格式轉換（PNG、JPEG、WebP、BMP、TIFF、GIF、ICO）
- AI 超解析（Real-ESRGAN、SwinIR、BSRGAN、Real-CUGAN、Waifu2x）
- AI 去背（rembg）
- AI 物件移除（MobileSAM + LaMa 修補）
- 人臉修復（CodeFormer、GFPGAN）
- OCR 文字辨識（視覺語言模型）
- 調整、濾鏡、裁切

### 音訊工具
- 格式轉碼（MP3、WAV、FLAC、OGG、AAC、M4A、WMA、OPUS）
- 剪切、音量調整
- AI 語音轉文字（Faster-Whisper）+ 摘要
- AI 音源分離（Demucs 6 軌）
- AI 歌詞提取 + 精準對齊
- MIDI 匯出（Basic Pitch + FluidSynth）
- 透過本地 LLM 或雲端 API 翻譯

### 影片工具
- 格式轉碼（MP4、MKV、AVI、MOV、WebM 等）
- 剪切（Stream Copy）、音訊提取
- AI 字幕提取（Whisper）
- AI 字幕翻譯
- AI 補幀（RIFE）
- AI 超解析（Real-ESRGAN）

### 文件工具
- OCR 文字辨識（視覺語言模型）
- AI 翻譯
- PDF 分割、PDF 轉換

### 通用功能
- 多檔案批次處理 + Filmstrip 管理介面
- 深色 / 淺色主題，Glassmorphism 設計風格
- 即時任務進度追蹤
- 本地 + 雲端 AI 模型支援（Ollama、OpenAI、Gemini）
- 多語系：繁體中文、英文

---

## AI 模型

| 類別 | 模型 |
|------|------|
| **語音辨識** | Faster-Whisper（tiny / base / small / medium / large-v3） |
| **翻譯 LLM** | TranslateGemma（4B/12B/27B）、Qwen3（1.7B/4B/8B/14B） |
| **超解析** | Real-ESRGAN、SwinIR、BSRGAN、Real-CUGAN、Waifu2x |
| **人臉修復** | CodeFormer、GFPGAN v1.4 |
| **VLM（OCR）** | Qwen3-VL（2B/4B/8B）、InternVL2.5（1B/4B）、Gemma 3（4B/12B） |
| **音源分離** | Demucs HTDemucs 6 軌 |
| **精準對齊** | Wav2Vec2（16 種語言） |
| **影片補幀** | RIFE v4.22 / v4.25 |
| **物件分割** | MobileSAM |

模型透過內建的模型管理器按需下載。

---

## 技術架構

```
前端：Vue 3 + TypeScript + Pinia + Vite
後端：FastAPI + Python 3.12 + uv
AI：  PyTorch / CTranslate2 / llama-server
媒體：FFmpeg / FluidSynth
```

---

## 架構概覽

```mermaid
graph TB
    subgraph Frontend["Vue 3 前端 (port 8000)"]
        UI[ToolLayout + Composables]
    end

    subgraph Backend["FastAPI 後端 (port 8001)"]
        direction LR
        Routes[Routes] --> Services --> Engine
    end

    subgraph AI["AI 推理引擎"]
        Llama["llama-server<br/>(LLM, VLM)"]
        PT["PyTorch<br/>(CV, STT, Demucs)"]
    end

    UI -->|"REST API"| Routes
    Engine --> Llama
    Engine --> PT
    Engine --> FFmpeg["FFmpeg"]
```

詳見 [架構文件](ARCHITECTURE.md)。

---

## 快速開始

### 環境需求

- **Node.js** 18+
- **Python** 3.12（透過 [uv](https://docs.astral.sh/uv/) 管理）
- **NVIDIA GPU** + CUDA（建議 6GB+ VRAM），也支援 CPU 模式

### 安裝

```bash
git clone https://github.com/sw-willie-wu/MediaTranX.git
cd MediaTranX

# 後端
cd backend
uv sync

# 手動下載二進位工具（FFmpeg、FluidSynth、llama-server）到 bin/

# 前端
cd ../frontend
npm install
```

### 啟動

```bash
# 終端 1：後端（port 8001）
cd backend
uv run python -m app.main --mode dev --port 8001

# 終端 2：前端（port 8000）
cd frontend
npm run dev
```

開啟瀏覽器 `http://localhost:8000`。

### 環境變數

後端透過環境變數設定（pydantic-settings，前綴 `MEDIATRANX_`）：

| 變數 | 說明 | 預設值（dev） |
|------|------|--------------|
| `MEDIATRANX_PATH__DATA` | 資料根目錄 | `.`（cwd） |
| `MEDIATRANX_PATH__VENV` | Python venv 路徑 | `.venv` |
| `MEDIATRANX_PATH__BIN` | 二進位工具目錄 | `bin` |
| `MEDIATRANX_PATH__MODELS` | AI 模型目錄 | `models` |
| `MEDIATRANX_DB__DSN` | 資料庫連線字串 | `sqlite:///mediatranx.db` |
| `MEDIATRANX_SERVER__MODE` | `production` 或 `dev` | `production` |

開發模式下也可以寫在後端目錄的 `.env` 檔案中。

### 下載 AI 模型

啟動後，到 **設定 > AI 模型** 下載所需模型。

---

## 文件

- [架構文件](ARCHITECTURE.md) — 系統概覽、API 端點、資料流
- [後端開發規範](BACKEND_DEVELOP_SPEC.md) — 後端開發規則
- [前端開發規範](FRONTEND_DEVELOP_SPEC.md) — UI/UX 規範

---

## 授權

MIT — 詳見 [LICENSE](../LICENSE)。
