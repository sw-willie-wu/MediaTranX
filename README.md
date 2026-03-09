# MediaTranX

基於 AI 的現代化多媒體處理桌面應用，整合語音辨識、翻譯、圖片超解析與媒體轉檔功能。

## 功能

| 模組 | 功能 |
|------|------|
| **影片** | 格式轉碼、AI 語音字幕生成、字幕翻譯 |
| **圖片** | 格式轉換、AI 超解析（2x/3x/4x）、去背、人臉修復 |
| **音訊** | 格式轉換 |
| **文件** | AI 翻譯 |

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

## 技術架構

```
Electron (Desktop Shell)
  └── Vue 3 + TypeScript + Pinia (Frontend, port 8000)
  └── FastAPI + Python 3.12 (Backend, port 8001)
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
# 安裝 Electron 依賴
cd src/electron
npm install

# 啟動開發環境（Vite + Python + Electron 一鍵啟動）
npm run electron
```

**重啟**

```bash
taskkill //F //IM electron.exe
taskkill //F //IM node.exe
taskkill //F //IM python.exe
cd src/electron && npm run electron
```

詳見 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 文件

- [架構文件](docs/ARCHITECTURE.md)
- [開發規範](docs/DEVELOPMENT.md)
- [打包策略](docs/BUILD_STRATEGY.md)
