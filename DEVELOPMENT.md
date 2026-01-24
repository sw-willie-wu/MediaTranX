# MediaTranX 開發文件

## 專案概述

MediaTranX 是一個桌面應用程式，用於影音處理，包含以下功能：
- 影片字幕處理（添加、提取、自動生成）
- 字幕翻譯（多語言、格式轉換）
- 影片調整（解析度、顏色、裁剪、幀率）
- 影片轉檔（格式/編碼轉換）
- AI 圖片處理（放大、去背、修復、人臉增強）

## 技術架構

```
┌─────────────────────────────────────────────────────────────┐
│                      MediaTranX                              │
├─────────────────────────────────────────────────────────────┤
│  GUI 層 - Electron (無邊框視窗 + 原生動畫)                   │
│  └─ src/frontend/main.js, preload.js                        │
├─────────────────────────────────────────────────────────────┤
│  前端 - Vue 3 + TypeScript + Pinia                          │
│  └─ src/frontend/src/                                       │
├─────────────────────────────────────────────────────────────┤
│  後端 - FastAPI + Uvicorn (port 8001)                       │
│  └─ src/backend/                                            │
├─────────────────────────────────────────────────────────────┤
│  核心處理層                                                  │
│  ├─ FFmpeg (影音處理)                                       │
│  ├─ faster-whisper (語音轉字幕)                             │
│  ├─ TranslateGemma (字幕翻譯)                               │
│  └─ Real-ESRGAN / GFPGAN / rembg (AI 圖片)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 已完成項目 ✅

### 第一階段：基礎建設

#### 1. 後端目錄結構
```
src/backend/
├── __init__.py                 # 伺服器啟動
├── main.py                     # FastAPI 應用
├── api/
│   ├── __init__.py             # 路由建構器
│   ├── middleware.py           # 請求中間件
│   ├── routes/
│   │   ├── __init__.py         # 路由匯總
│   │   ├── health.py           # GET /api/health, /api/device
│   │   ├── files.py            # 檔案上傳/下載 API
│   │   └── tasks.py            # 任務狀態/進度 SSE
│   └── schemas/
│       ├── __init__.py
│       └── common.py           # TaskResponse, FileInfo 等
├── core/
│   ├── __init__.py
│   └── device.py               # GPU/CPU 自動偵測
├── workers/
│   ├── __init__.py
│   ├── task_manager.py         # 任務佇列管理
│   └── progress_tracker.py     # SSE 進度推送
├── services/
│   ├── __init__.py
│   └── file_service.py         # 檔案管理服務
└── configs/
    └── __init__.py             # 設定類別
```

#### 2. API 端點
| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/health` | 健康檢查 |
| GET | `/api/device` | 取得裝置資訊 (GPU/CPU) |
| POST | `/api/files/upload` | 上傳檔案 |
| GET | `/api/files/{id}` | 取得檔案資訊 |
| GET | `/api/files/{id}/download` | 下載檔案 |
| DELETE | `/api/files/{id}` | 刪除檔案 |
| GET | `/api/tasks` | 列出所有任務 |
| GET | `/api/tasks/{id}` | 取得任務狀態 |
| GET | `/api/tasks/{id}/progress` | SSE 進度串流 |
| POST | `/api/tasks/{id}/cancel` | 取消任務 |
| DELETE | `/api/tasks/{id}` | 移除任務 |

#### 3. 前端架構
```
src/frontend/src/
├── main.ts                     # 應用入口 (已加入 Pinia)
├── stores/
│   ├── index.ts
│   ├── tasks.ts                # 任務狀態管理
│   ├── files.ts                # 檔案狀態管理
│   └── settings.ts             # 設定狀態
├── composables/
│   ├── index.ts
│   ├── useApi.ts               # API 客戶端封裝
│   └── useProgress.ts          # SSE 進度追蹤
├── components/common/
│   ├── ProgressBar.vue         # 進度條組件
│   └── TaskQueue.vue           # 任務列表組件
└── types/
    ├── index.ts
    ├── task.ts                 # 任務類型定義
    ├── media.ts                # 媒體類型定義
    └── api.ts                  # API 類型定義
```

#### 4. GPU/CPU 自動偵測
- 自動偵測 NVIDIA GPU (CUDA)
- 支援 Apple Silicon (MPS)
- CPU 降級支援（使用 int8 量化）

---

## 待完成項目 📋

### 第二階段：影片轉檔

| 項目 | 檔案位置 | 說明 |
|------|----------|------|
| FFmpeg 封裝 | `backend/core/ffmpeg.py` | FFmpeg 命令執行、進度解析 |
| 轉檔服務 | `backend/services/video/transcode_service.py` | 轉檔業務邏輯 |
| 轉檔路由 | `backend/api/routes/video/transcode.py` | 轉檔 API 端點 |
| 轉檔面板 | `frontend/src/components/video/TranscodePanel.vue` | 轉檔 UI |
| 影片頁面 | `frontend/src/views/VideoView.vue` | 影片功能主頁 |

**API 設計：**
```
POST /api/video/transcode
請求：
{
  "file_id": "xxx",
  "output_format": "mp4",
  "video_codec": "h264",
  "audio_codec": "aac",
  "quality_preset": "medium"
}
回應：
{
  "task_id": "xxx"
}
```

### 第三階段：字幕功能

| 項目 | 檔案位置 | 說明 |
|------|----------|------|
| Whisper 封裝 | `backend/core/whisper.py` | faster-whisper STT |
| 字幕服務 | `backend/services/video/subtitle_service.py` | 字幕處理邏輯 |
| 字幕路由 | `backend/api/routes/video/subtitles.py` | 字幕 API |
| 翻譯封裝 | `backend/core/translator.py` | TranslateGemma |
| 翻譯服務 | `backend/services/subtitle/translation_service.py` | 翻譯邏輯 |
| 字幕面板 | `frontend/src/components/video/SubtitlePanel.vue` | 字幕 UI |

**API 設計：**
```
POST /api/video/subtitle/generate   # 語音轉字幕
POST /api/video/subtitle/add        # 添加字幕（燒入/軟字幕）
POST /api/video/subtitle/extract    # 提取字幕
POST /api/subtitle/translate        # 翻譯字幕
```

### 第四階段：影片調整

| 項目 | 檔案位置 | 說明 |
|------|----------|------|
| 調整服務 | `backend/services/video/adjustment_service.py` | 影片調整邏輯 |
| 調整路由 | `backend/api/routes/video/adjustments.py` | 調整 API |
| 調整面板 | `frontend/src/components/video/AdjustmentPanel.vue` | 調整 UI |

**API 設計：**
```
POST /api/video/adjust/resolution   # 解析度調整
POST /api/video/adjust/color        # 顏色調整
POST /api/video/adjust/trim         # 裁剪
POST /api/video/adjust/framerate    # 幀率調整
```

### 第五階段：AI 圖片處理

| 項目 | 檔案位置 | 說明 |
|------|----------|------|
| 模型載入器 | `backend/core/model_loader.py` | AI 模型延遲載入 |
| 放大服務 | `backend/services/image/upscale_service.py` | Real-ESRGAN |
| 去背服務 | `backend/services/image/background_service.py` | rembg |
| 人臉增強 | `backend/services/image/face_service.py` | GFPGAN |
| 圖片路由 | `backend/api/routes/image/*.py` | 圖片 API |
| 圖片面板 | `frontend/src/components/image/*.vue` | 圖片 UI |

**API 設計：**
```
POST /api/image/upscale             # AI 放大 (2x/4x)
POST /api/image/remove-background   # 去背
POST /api/image/enhance             # 增強
POST /api/image/face-enhance        # 人臉增強
```

---

## 安裝指南

### Python 環境
```bash
# 安裝依賴
pip install -r requirements.txt

# GPU 版本 PyTorch (可選)
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### 前端環境
```bash
cd src/frontend

# 安裝依賴
npm install

# 安裝 Pinia (狀態管理)
npm install pinia
```

### FFmpeg
需要另外安裝 FFmpeg 並加入系統 PATH：
- Windows: https://www.gyan.dev/ffmpeg/builds/
- 或使用 `choco install ffmpeg`

---

## 啟動方式

### 開發模式 (Electron)
```bash
# 終端 1: 啟動前端 Vite dev server (port 8000)
cd src/frontend
npm run dev

# 終端 2: 啟動 Electron (會自動啟動 Python 後端於 port 8001)
cd src/frontend
npm run electron:serve
```

### 生產模式
```bash
# 建構前端
cd src/frontend
npm run build

# 打包 Electron 應用 (待實作)
npm run electron:build
```

### 注意事項
- Vite dev server 運行於 port 8000
- Python FastAPI 後端運行於 port 8001
- Vite 會自動 proxy `/api` 請求到後端

---

## 目錄結構總覽

```
MediaTranX/
├── src/
│   ├── main.py                 # 應用入口
│   ├── backend/                # FastAPI 後端
│   ├── frontend/               # Vue 3 前端
│   └── gui/                    # pywebview 視窗
├── models/                     # AI 模型權重 (需下載)
│   ├── realesrgan/
│   ├── gfpgan/
│   ├── rembg/
│   └── whisper/
├── temp/                       # 暫存檔案
├── output/                     # 輸出目錄
├── requirements.txt            # Python 依賴
├── DEVELOPMENT.md              # 本文件
└── README.md
```

---

## 技術選型說明

| 技術 | 選擇 | 原因 |
|------|------|------|
| 語音轉字幕 | faster-whisper | 速度快 4 倍，記憶體用量少 |
| 字幕翻譯 | TranslateGemma | Google 本地模型，完全離線 |
| 圖片放大 | Real-ESRGAN | 業界標準，效果優秀 |
| 人臉增強 | GFPGAN | 專門針對人臉優化 |
| 去背 | rembg | 輕量快速，效果好 |
| GUI | Electron | 原生視窗動畫，成熟的無框視窗支援 |
| 前端框架 | Vue 3 | 生態完整，TypeScript 支援好 |
| 狀態管理 | Pinia | Vue 3 官方推薦 |

---

## 注意事項

1. **GPU 記憶體**：AI 模型需要較多記憶體，建議至少 4GB VRAM
2. **首次啟動**：AI 模型會在首次使用時自動下載
3. **FFmpeg**：必須安裝 FFmpeg 才能使用影音處理功能
4. **模型路徑**：AI 模型預設存放在 `models/` 目錄
