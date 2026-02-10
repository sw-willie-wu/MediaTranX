# TranslateGemma 效能分析

## 測試環境
- GPU: NVIDIA GeForce RTX 3080 (10GB VRAM, 760 GB/s bandwidth)
- 測試資料: 10 段日文字幕翻譯成繁體中文

## 效能測試結果

| 模型 | 總時間 | 每段時間 | GPU 使用率 | VRAM 使用 |
|------|--------|----------|------------|-----------|
| 4b   | 6.78s  | 0.68s    | 66-79%     | 5343 MB   |
| 12b  | 41.85s | 4.19s    | 32%        | 8765 MB   |

**結論：12b 比 4b 慢約 6 倍**

## 12b 模型記憶體配置

```
offloaded 49/49 layers to GPU     ← 全部層都在 GPU
CUDA0 model buffer = 6956.38 MiB  ← 模型權重 (~7GB)
CPU_Mapped buffer  = 787.69 MiB   ← embedding 在 CPU
KV buffer          = 384.00 MiB   ← KV cache
compute buffer     = 519.62 MiB   ← 計算暫存
```

## 12b 慢的原因：記憶體頻寬瓶頸 (Memory-Bound)

1. **全部 49 層都在 GPU 上**，不是 CPU 拖慢速度
2. GPU 使用率只有 32% 是因為模型是 **memory-bound**
3. 每生成一個 token，GPU 需要讀取 ~7GB 模型權重
4. RTX 3080 頻寬 760 GB/s，但模型太大，讀取權重成為瓶頸
5. 相比之下，4b 模型 (~2.5GB) 讀取更快，GPU 使用率達 79%

## 建議

### 追求速度
- 使用 4b 模型 (每段 0.68s，快 6 倍)
- 翻譯品質會稍差，但速度大幅提升

### 追求品質
- 使用 12b 模型 (每段 4.19s)
- 適合不急的離線翻譯任務

### 硬體升級
- RTX 4090 有 1 TB/s 頻寬，理論上 12b 會快 30-40%
- 或使用 24GB VRAM 的顯卡避免任何 CPU fallback

## 技術細節

### 模型參數
| 模型 | 層數 | GGUF 大小 | n_ctx | VRAM overhead |
|------|------|-----------|-------|---------------|
| 4b   | 26   | ~2.5 GB   | 2048  | 400 MB        |
| 12b  | 48   | ~7.3 GB   | 1024  | 800 MB        |
| 27b  | 64   | ~16.5 GB  | 512   | 1200 MB       |

### 已知問題與修復
1. **Deadlock 問題**：`translate_segments()` 和 `_unload_model()` 都要取得 `self._lock`，導致死鎖
   - 修復：將 `threading.Lock()` 改為 `threading.RLock()` (可重入鎖)

2. **VRAM 檢測時機**：evict 其他模型後，CUDA 記憶體可能還沒完全釋放
   - 修復：evict 後加入 0.5 秒延遲，並多次檢查 VRAM

3. **Keepalive 訊息**：翻譯超過 30 秒沒有進度更新就會出現
   - 修復：將 batch_size 從 10 改為 5，更頻繁更新進度
