# MediaTranX Frontend Style Guide

> 所有前端開發必須遵守本文件。新增頁面、元件或修改現有 UI 前請先閱讀。

---

## 1. 設計語言

### 視覺風格
- **Glassmorphism**：半透明面板 + `backdrop-filter: blur(20px)`，整體有層次感
- 深色為預設主題，同時支援淺色主題
- 背景為漸層（`--bg-gradient-start` → `--bg-gradient-end`），不使用純色背景

### 圓角規範
| 層級 | 數值 | 使用場景 |
|------|------|---------|
| 大 | `12px` | 主面板、卡片（`function-sidebar`、`settings-panel`、`preview-area`）|
| 中 | `8px` | 按鈕、輸入框、下拉選單 |
| 小 | `6px` | Badge、Tag、tooltip |
| 圓形 | `50%` | 圓形按鈕（slider grip 等）|

---

## 2. CSS 設計 Token

**所有顏色、背景、邊框都必須使用 CSS 變數，禁止寫死 hex 色值（主題切換會失效）。**

### 語意色彩（兩個主題共用）
```css
--color-primary: #7c6fad        /* 主要 CTA、active 狀態 */
--color-primary-hover: #6558a0  /* hover 加深 */
--color-accent: #a89cc8         /* accent bar、選中標記 */
--color-success: #10b981
--color-danger: #ef4444
--color-warning: #f59e0b
--color-info: #6366f1
```

### 文字層級
```css
--text-primary    /* 主要文字、標題 */
--text-secondary  /* 次要文字（label、描述）*/
--text-muted      /* 輔助文字、placeholder */
--text-disabled   /* 禁用狀態文字 */
```

### 面板（Panel）
```css
--panel-bg         /* 面板背景（半透明）*/
--panel-bg-hover   /* hover 狀態 */
--panel-bg-active  /* active/selected 狀態 */
--panel-border     /* 面板邊框 */
--panel-border-hover
```

### 輸入框
```css
--input-bg         /* 輸入框背景 */
--input-bg-focus   /* focus 狀態背景 */
--input-border     /* 輸入框邊框 */
--input-border-focus
```

---

## 3. 字體排版

| 用途 | font-size | color |
|------|-----------|-------|
| 正文 | `15px`（body 預設）| `--text-primary` |
| 設定區塊標題（settings-title）| `1rem` / `font-weight: 500` | `--text-primary` |
| 表單 label | `0.85rem` | `--text-secondary` |
| 提示文字（form-hint）| `0.75rem` | `--text-muted` |
| 工具列按鈕 tooltip | `0.8rem` | `--text-primary` |
| Badge | `0.6rem` / `font-weight: 600` | `#fff` |

---

## 4. 間距系統

使用 `rem` 為單位，基準 `1rem = 15px`：

| Token | 數值 | 常見使用 |
|-------|------|---------|
| xs | `0.25rem` | 極小間距 |
| sm | `0.5rem` | form-group 內部間距 |
| md | `0.75rem` | 元件間距 |
| lg | `1rem` | 面板 padding、section 間距 |
| xl | `1.5rem` | 大區塊間距 |

---

## 5. 動畫與過渡

- 互動回饋（hover、active）：`transition: all 0.15s ease`
- 狀態切換（顯示/隱藏元素）：`transition: opacity 0.2s ease`
- 主題切換：`transition: background 0.3s ease, color 0.3s ease`
- 主畫面進場：`animation: fadeIn 0.4s ease`
- 禁止使用超過 `0.4s` 的過渡動畫（操作回饋應即時）

---

## 6. 元件規範

### 6.1 已有共用元件（優先使用，不重複造輪）

| 元件 | 路徑 | 用途 |
|------|------|------|
| `AppSelect` | `components/common/AppSelect.vue` | 所有下拉選單 |
| `AppRange` | `components/common/AppRange.vue` | 所有滑桿 |
| `AppUploadZone` | `components/common/AppUploadZone.vue` | 檔案上傳區域 |
| `AppMediaInfoBar` | `components/common/AppMediaInfoBar.vue` | 預覽區底部媒體資訊欄 |
| `AppToast` | `components/AppToast.vue` | 所有 Toast 通知（透過 `useToast` composable）|
| `AppButtonGroup` | `components/common/AppButtonGroup.vue` | 分段選擇按鈕（如放大倍率 2x/3x/4x）|

> **`AppButtonGroup`** 取代各 View 中重複定義的 `.scale-btn` 群組。

### 6.2 待建立元件

| 元件 | 用途 |
|------|------|
| `AppButtonGroup.vue` | 分段選擇（toggle button group）|
| `AppToggleSwitch.vue` | Boolean 開關（取代各處自製 toggle-switch）|

---

## 7. 按鈕模式

### 主要 CTA（執行按鈕）
```scss
// 唯一樣式來源：ToolLayout 的 .execute-btn
// 不在各 View 的 settings slot 裡自行定義執行按鈕
background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
border-radius: 8px;
color: white;
font-size: 0.9rem;
font-weight: 500;

&:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
}
&:disabled { opacity: 0.5; cursor: not-allowed; }
```

### 次要按鈕（dismiss / cancel）
```scss
background: transparent;
border: 1px solid var(--panel-border);
border-radius: 6px;
color: var(--text-muted);

&:hover { color: var(--text-primary); border-color: var(--text-muted); }
```

### 分段選擇按鈕（AppButtonGroup）
```scss
// 未選中
background: var(--input-bg);
border: 1px solid var(--input-border);
color: var(--text-secondary);

// 選中（active）
background: rgba(96, 165, 250, 0.2);
border-color: var(--color-accent);
color: var(--color-accent);
```

### Toolbar 按鈕（預覽區浮層按鈕）
- 尺寸：`32×32px`
- 預設背景：`rgba(0, 0, 0, 0.4)`，`opacity: 0.7`
- hover：`opacity: 1`
- Tooltip：使用 `data-tooltip` + CSS `::after`（同 MainSidebar 的 nav-btn 樣式）
- 危險操作（刪除）hover：`background: rgba(220, 53, 69, 0.8)`
- Disabled：`opacity: 0.3; cursor: not-allowed; pointer-events: none`

---

## 8. 表單模式（設定面板）

**所有 View 的設定面板遵循相同結構，樣式定義於 `assets/styles/_tool-settings.scss`，不在各 View 重複定義。**

```html
<!-- 一個功能區塊 -->
<div class="function-settings">
  <h6 class="settings-title">
    <i class="bi bi-xxx me-2"></i>區塊標題
  </h6>

  <div class="form-group">
    <label>欄位名稱</label>
    <AppSelect v-model="..." :options="..." />
    <small class="form-hint">輔助說明文字</small>
  </div>

  <div class="form-group">
    <label>滑桿名稱: {{ value }}%</label>
    <AppRange v-model="..." :min="0" :max="100" />
  </div>

  <div class="form-group">
    <label>分段選擇</label>
    <AppButtonGroup v-model="..." :options="..." />
  </div>

  <div class="form-group">
    <AppToggleSwitch v-model="..." label="開關說明" />
    <small class="form-hint">輔助說明</small>
  </div>
</div>
```

### 共用 SCSS（`_tool-settings.scss`）
```scss
.function-settings {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.settings-title {
  display: flex;
  align-items: center;
  font-size: 1rem;
  font-weight: 500;
  margin: 0;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--panel-border);
  color: var(--text-primary);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  label { font-size: 0.85rem; color: var(--text-secondary); }
}

.form-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
}
```

---

## 9. 選中狀態（Active Indicator）

**所有 sidebar/nav 類的選中狀態使用左側 accent bar，禁止僅用背景色區分（與 hover 重疊）。**

```scss
// 通用 active 樣式
&.active {
  color: var(--text-primary);
  background: var(--panel-bg-active);

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 20%;
    bottom: 20%;
    width: 3px;
    border-radius: 0 2px 2px 0;
    background: var(--color-accent);
  }
}
```

適用：
- `ToolLayout` 的 `.function-item`（子功能列表）
- `SettingsView` 的 sidebar tab

---

## 10. 工具頁面架構（ToolLayout 模式）

所有工具頁面使用 `ToolLayout` 的三欄結構：

```
┌──────────┬──────────────────────────┬────────────┐
│  180px   │       flex: 1            │   320px    │
│  子功能  │       預覽區域           │  設定面板  │
│  列表    │                          │            │
│          │                          │  ... 設定  │
│          │                          │  ... 項目  │
│          │                          ├────────────┤
│          │                          │ [▶ 執行]   │
└──────────┴──────────────────────────┴────────────┘
```

### 規則

1. **執行按鈕必須在 ToolLayout 底部**（透過 `:execute-disabled`、`:execute-loading`、`execute-label`、`@execute` props 控制），禁止在 settings slot 內放第二個執行按鈕
2. **未完成功能**：在 `subFunctions` 加 `comingSoon: true`，ToolLayout 自動顯示 badge 並隱藏執行按鈕
3. **設定面板樣式**：使用 `_tool-settings.scss` 提供的 class，不在各 View 重複定義

### 預覽區 Toolbar（有載入檔案時顯示）

預覽區右上角直排 toolbar，由上到下固定順序：

```
[ ✕ 移除 ]    ← 有檔案就啟用
[ ⧉ 比對 ]    ← 有結果才啟用（toggle）
[ ↓ 下載 ]    ← 有結果才啟用
```

- 三個按鈕**永遠渲染**，無結果時比對/下載顯示 disabled 樣式
- 整組 toolbar 僅在 `hasFile === true` 時顯示
- 比對為 toggle 模式（active 狀態高亮）
- 下載觸發 `window.electron.saveFileDialog()`

---

## 11. 通知系統

使用 `useToast()` composable，禁止直接操作 DOM 或用 `alert()`。

### Toast 類型
| 類型 | icon | 使用場景 |
|------|------|---------|
| `success` | `bi-check-circle` | 任務提交成功、操作完成 |
| `error` | `bi-x-circle` | 錯誤、失敗 |
| `info` | `bi-info-circle` | 一般提示 |

### 任務完成 Toast（帶 Action）
任務完成後的 toast 必須帶下載 action：
```ts
toast.show('超解析 4x 完成', {
  type: 'success',
  icon: 'bi-check-circle',
  action: { label: '下載', callback: () => downloadResult(taskId) }
})
```

---

## 12. 數字與單位格式

| 資料類型 | 格式 | 範例 |
|---------|------|------|
| 解析度 | `W × H`（Unicode 乘號）| `1920 × 1080` |
| 時間長度 | `m:ss` / `h:mm:ss` | `3:45`、`1:23:45` |
| 檔案大小 | 自動單位（B / KB / MB / GB）| `1.2 MB` |
| 位元率 | 自動單位（bps / Kbps / Mbps）| `5.2 Mbps` |
| 進度 | 百分比，無小數 | `42%` |
| 縮放比例 | 百分比，無小數 | `150%` |

---

## 13. 禁止事項

- 禁止硬寫色值（`#ffffff`、`rgba(...)` 等），必須使用 CSS 變數
- 禁止在各 View 重複定義 `.settings-title`、`.form-group`、`.form-hint` 等共用樣式
- 禁止在 settings slot 內放執行按鈕（統一走 ToolLayout 底部）
- 禁止使用 `alert()`、`confirm()`（使用 Toast 或 Modal）
- 禁止對未完成功能顯示正常可用的 UI（必須加 `comingSoon` 標記）
- 禁止在 `<style>` 中使用非 scoped 的全域樣式（全域樣式集中在 `assets/`）
