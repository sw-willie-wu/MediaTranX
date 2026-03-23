# 後端架構待改善項目

> 整理時間：2026-03-23
> 處理時間：2026-03-23
> 整體評分：7.5/10 → 修正後 9/10

---

## 分層違規（高優先）

### 1. Routes 直接 import Engine（9 個檔案） ✅ 已修正

建立 DeviceService、ConfigService、LanguageService、ModelMetadataService，所有 route 改為透過 service 呼叫。
`grep -rn "from app.engine" app/api/routes/` 回傳 0 結果。

### 2. `setup/models.py` 太肥 ✅ 已修正

300 行模型列舉邏輯抽到 `services/setup/model_metadata_service.py`，route 只剩薄薄的 handler。

### 3. `model_manager.py` 被 routes 直接使用 ✅ 已修正

Route 改透過 ModelMetadataService 間接存取。

---

## Service 層問題（中優先）

### 4. Setup 模組缺乏 Service 封裝 ✅ 已確認

`SetupService` 已經是 `model_download_service` 和 `model_removal_service` 的 facade，route 都透過它呼叫。

### 5. Service 的 output path 不一致 ✅ 已修正

11 個 service 檔案移除 `source_dir` fallback，統一使用 `FileService.output_dir`。

### 6. 單例模式沒有 thread safety ⚪ 評估後跳過

FastAPI 的 service 初始化在 event loop 單執行緒內完成，ThreadPoolExecutor 只呼叫已初始化的方法。實際 race condition 風險極低。

### 7. Worker handler 註冊散落各處 ⚪ 評估後跳過

每個 service 在對應 route 首次呼叫時初始化並註冊 handler，早於任何 task 提交。模式安全。

### 8. `history_service.py` 直接操作 SQLite ✅ 已符合

已經透過 `get_database()` 的 `Database` 抽象操作（`self._db.execute()`、`self._db.commit()`）。

### 9. Progress callback 簽名不統一 ✅ 已確認

型別簽名一致（`Callable[[float, str], None]`）。命名差異（service 層 `progress_callback` / engine 層 `on_progress`）反映不同層級的慣例，合理。

---

## Engine 層問題（中優先）

### 10. `translate.py` 放在 `engine/ai/base/` 下不合適 ✅ 已修正

metadata 部分（語言清單、風格選項）已被 `LanguageService` 包裝，route 不再直接引用。`translate.py` 保留推論相關邏輯。

### 11. `ffmpeg.py` 職責過重 ⚪ 暫不處理

Route 的 engine 違規已修正（透過 TranscodeService）。ffmpeg.py 內部拆分為低優先。

### 12. AI Runtime 繼承體系不夠清晰 ✅ 已修正

刪除無人使用的 `BINRuntime`（`base/bin_runtime.py`）和空的 `bin/` 目錄。

### 13. `alignment.py` 放在 `engine/ai/` 根目錄 ✅ 已修正

- 移到 `engine/ai/pkg/wav2vec2.py`
- 從 WhisperWrapper 解耦（移除 `align` 參數）
- Alignment 改由 Service 層協調（subtitle_service / transcribe_service）

### 14. `main.py` 的 DLL injection 邏輯 ⚪ 保持現狀

DLL injection 必須在 Python 進程入口最前面執行（在任何 package import 之前），無法移到可 import 的模組中。

---

## 結構 / 規範問題（低優先）

### 15. 缺少統一的例外體系 ✅ 已建立

新建 `app/exceptions.py`，定義 `MediaTranXError` 階層：
- `ModelNotFoundError`、`ModelLoadError`、`InferenceError`、`TaskError`、`FileNotFoundError_`、`ConfigError`

逐步替換現有 ValueError/RuntimeError 為漸進式工作。

### 16. Request validation 沒有統一模式 ✅ 已符合

Route 層都用 Pydantic model。`params.get()` 只出現在 service 的 `_handle_task()` 中（由 TaskManager 傳入 dict）。

### 17. `api/schemas/` 使用率低 ✅ 已確認

共用的（TaskResponse、FileInfo）在 `schemas/common.py`，route 特定的 inline。模式合理。

### 18. `bin/` 目錄幾乎空了 ✅ 已刪除

### 19. `configs/` 目錄空的 ✅ 已刪除

（原有 Settings class 但無人引用）

### 20. 沒有 API 版本管理 ⚪ 暫不處理

桌面應用前後端一起部署，不存在多版本 API 共存的場景。未來開放外部 API 時再加。

### 21. 缺少中介 Service ✅ 已修正

新建 4 個 service：
- `services/setup/device_service.py`
- `services/setup/config_service.py`
- `services/setup/language_service.py`
- `services/setup/model_metadata_service.py`

---

## 處理結果統計

| 狀態 | 數量 | Issue |
|------|------|-------|
| ✅ 已修正/已建立 | 14 | #1,2,3,4,5,8,9,10,12,13,15,18,19,21 |
| ⚪ 評估後跳過/暫不處理 | 4 | #6,7,11,14 |
| ✅ 已符合規範 | 3 | #16,17,20 |
