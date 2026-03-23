# MediaTranX

基於 AI 的現代化多媒體處理應用，整合語音辨識、翻譯、圖片處理、OCR 與媒體轉檔功能。

## 功能

| 模組 | 功能 |
|------|------|
| **影片** | 格式轉碼、剪切、AI 語音字幕生成、字幕翻譯 |
| **圖片** | 格式轉換、裁切、濾鏡調整、AI 超解析、去背、物件移除、人臉修復、OCR |
| **音訊** | 格式轉換、剪切、音量調整、AI 語音轉文字 |
| **文件** | AI 翻譯、OCR、PDF 轉換、文件分割 |

支援中文（繁體）與英文介面。

## AI 模型支援

**語音辨識（STT）**
- Faster-Whisper（tiny / base / small / medium / large-v3）

**翻譯（LLM）**
- TranslateGemma（4B / 12B / 27B）
- Qwen3（1.7B / 4B / 8B / 14B）

**圖片超解析**
- Real-ESRGAN（x2plus / x4plus / x4plus-anime）
- SwinIR（lightweight / classical / realworld）
- BSRGAN
- Real-CUGAN（2x / 3x / 4x，支援降噪選項）
- Waifu2x（CUnet）

**人臉修復**
- CodeFormer
- GFPGAN v1.4

**OCR（VLM）**
- Qwen3-VL（2B / 4B / 8B）
- InternVL2.5（1B / 4B）
- Gemma 3（4B / 12B）

**物件分割**
- MobileSAM

## 技術架構

```
Vue 3 + TypeScript + Pinia (Frontend, port 8000)
FastAPI + Python 3.12 (Backend, port 8001)
  └── AI Sidecar (.venv in %APPDATA%)
```

詳見 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 開發環境

**需求**
- Node.js 18+
- Python 3.12（透過 uv 管理）
- NVIDIA GPU（CUDA，建議 6GB+ VRAM）

**啟動**

```bash
# Frontend
cd frontend
npm install
npm run dev

# Backend
cd backend
uv run uvicorn app.main:app --reload
```

詳見 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 文件

- [架構文件](docs/ARCHITECTURE.md)
- [後端架構](docs/BACKEND_ARCHITECTURE.md)
- [前端設計系統](docs/FRONTEND_DESIGN_SYSTEM.md)
- [開發規範](docs/DEVELOPMENT.md)
