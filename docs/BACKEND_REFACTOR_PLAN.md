# 後端架構 21 Issue 修正計畫

## Context

完整 review 後端架構，發現 21 個待改善項目（詳見 `BACKEND_ISSUES.md`）。按依賴關係排序處理，每處理完一個確認該 issue 完全解決後才進入下一個。

## 處理順序與分組

依賴關係決定順序：先建 service 基礎設施，再修 route 違規，最後清理結構。

---

### Phase 1: 建立缺少的 Service（Issue 21, 4, 5）

**Issue 21: 新增中介 Service**
- 新建 `services/setup/device_service.py` — 包裝 `engine.device` 的查詢
- 新建 `services/setup/config_service.py` — 包裝 `engine.paths` 的 config 操作
- 新建 `services/setup/model_metadata_service.py` — 從 `routes/setup/models.py` 抽出 300 行模型列舉邏輯
- 新建 `services/setup/language_service.py` — 包裝語言/翻譯風格常數查詢
- 所有 service 遵循單例模式 + 工廠函數

**Issue 4: Setup 模組封裝**
- `model_download_service.py` 的 `handle_model_download()` 包成 Service class
- `model_removal_service.py` 的 `handle_model_removal()` 包成 Service class
- 或合併進 `manager_service.py`（SetupService）
- 加上工廠函數

**Issue 5: output path 統一**
- 全域搜尋 `source_dir` fallback
- 統一改用 `FileService.output_dir`

**驗證**：所有新 service 能正常 import，工廠函數能取得單例

---

### Phase 2: 修正 Route 分層違規（Issue 1, 2, 3）

**Issue 1: Routes 直接 import Engine（9 檔案）**
逐檔修改，改為呼叫 Phase 1 建立的 service：
- `health.py` → `DeviceService`
- `setup/config.py` → `ConfigService`
- `setup/models.py` → `ModelMetadataService`
- `audio/transcribe.py` → `LanguageService`
- `video/subtitle.py` → `LanguageService`
- `video/transcode.py` → 透過 `TranscodeService`
- `document/ocr.py` → 常數移到 service
- `document/translate.py` → `LanguageService`
- `image/ocr.py` → 常數移到 service

**Issue 2: `setup/models.py` 瘦身**
- 模型列舉邏輯已移到 `ModelMetadataService`
- Route 只剩 3-5 行：呼叫 service → 回傳

**Issue 3: ModelManager 不被 route 直接使用**
- Phase 2 完成後自然解決（route 改呼叫 ModelMetadataService）

**驗證**：`grep -r "from app.engine" app/api/routes/` 應該回傳 0 結果

---

### Phase 3: Service 層修正（Issue 6, 7, 8, 9）

**Issue 6: 單例 thread safety**
- 加 `threading.Lock` 保護 `__new__` 和 `_initialized`

**Issue 7: Handler 註冊集中化**
- 新建 `services/__init__.py` 的 `register_all_handlers()`
- 在 `app/api/__init__.py` 啟動時統一呼叫
- 各 service 的 `__init__` 不再自行註冊

**Issue 8: history_service 使用 database 抽象**
- 改為透過 `engine/database.py` 操作

**Issue 9: Progress callback 簽名統一**
- 統一為 `on_progress: Callable[[float, str], None]`
- 全域替換 `progress_callback` → `on_progress`

**驗證**：重啟 app，所有功能正常運作

---

### Phase 4: Engine 層整理（Issue 10, 11, 12, 13, 14）

**Issue 10: translate.py 歸位**
- metadata 部分（語言清單、風格選項）移到 `LanguageService`
- prompt template 保留在 engine（屬於推論邏輯）
- 檔案留在 `engine/ai/base/` 但只保留推論相關

**Issue 11: ffmpeg.py 拆分**
- `FFmpegInfo` — MediaInfo 查詢
- `FFmpegRunner` — 實際轉碼執行
- 或保持一個檔案但分成兩個 class

**Issue 12: Runtime 繼承體系清理**
- 刪除空的 `BINRuntime`
- 確認 `GGUFRuntime` / `LlamaServerRuntime` 關係
- 更新 `__init__.py` export

**Issue 13: alignment.py 歸位 + 改名 + 解耦**
- 移到 `engine/ai/pkg/wav2vec2.py`（改名反映實際使用的模型）
- 更新所有 import（`model_download_service.py`、`routes/setup/models.py`）
- **從 WhisperWrapper 移除 align 邏輯** — whisper.py 不再 import alignment
- Alignment 改由 Service 層協調：
  - `subtitle_service.py`：whisper.transcribe() → wav2vec2.align()
  - `transcribe_service.py`：同上
  - WhisperWrapper.transcribe() 移除 `align` 參數

**Issue 14: main.py DLL injection 移出**
- 移到 `engine/bootstrap.py`
- `main.py` 只呼叫 `bootstrap()`

**驗證**：import 路徑都正確，app 正常啟動

---

### Phase 5: 結構規範（Issue 15-20）

**Issue 15: 自訂 Exception**
- 新建 `app/exceptions.py`
- 定義 `MediaTranXError` 階層
- 逐步替換 `ValueError` / `RuntimeError`

**Issue 16: Request validation 統一**
- 確認所有 route 都用 Pydantic model
- 移除 `params.get()` 模式

**Issue 17: schemas/ 定位**
- 共用的（TaskResponse）留在 `schemas/`
- Route 特定的保持 inline
- 或全部移到 schemas/ — 看哪種一致

**Issue 18: 刪除空的 bin/ 目錄**

**Issue 19: 刪除空的 configs/ 目錄**

**Issue 20: API 版本前綴**
- Route prefix 從 `/api/` 改為 `/api/v1/`
- 前端 `apiFetch` base URL 同步更新

**驗證**：全部功能正常，前後端通訊正常

---

## 每個 Issue 的確認流程

處理完每個 issue 後：
1. `grep` 確認沒有殘留的舊 import / 舊模式
2. 確認相關檔案都已更新
3. 確認後才進入下一個 issue

## 檔案影響範圍

| Phase | 新建 | 修改 | 刪除 |
|-------|------|------|------|
| 1 | 4 service 檔案 | model_download/removal service | - |
| 2 | - | 9 route 檔案 | - |
| 3 | - | 多個 service、api/__init__ | - |
| 4 | bootstrap.py | ffmpeg.py、alignment.py、translate.py | bin/ |
| 5 | exceptions.py | routes、apiFetch | configs/ |
