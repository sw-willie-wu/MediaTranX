# MediaTranX Frontend Design System

> 所有前端 UI 元件必須遵循本規範。新增功能時先查閱此文件，不得在 component scoped style 中重複定義已有的共用樣式。

---

## 1. 設計語言

### 視覺風格
- **Glassmorphism**：半透明面板 + `backdrop-filter: blur(20px)`，整體有層次感
- 深色為預設主題，同時支援淺色主題
- 背景為漸層（`--bg-gradient-start` → `--bg-gradient-end`），不使用純色背景

### 設計原則
- **一致性**：相同用途的 UI 元素使用相同的樣式 class，不得各自實作
- **規範優先**：先找共用 class，找不到再向 `tool-panels-shared.scss` 新增，最後才寫 scoped style
- **最小化 scoped style**：scoped style 只用於該 component 獨有的版面邏輯，不重複定義顏色/間距/邊框

---

## 2. Design Tokens（CSS 變數）

定義於 `src/assets/base.css`。**所有顏色、背景、邊框都必須使用 CSS 變數，禁止寫死 hex 色值（主題切換會失效）。**

### 品牌色
| 變數 | 值 | 用途 |
|---|---|---|
| `--color-primary` | `#7c6fad` | 主要互動色、active 狀態 |
| `--color-primary-hover` | `#6558a0` | hover 狀態 |
| `--color-success` | `#10b981` | 成功/完成 |
| `--color-danger` | `#ef4444` | 錯誤/危險 |
| `--color-warning` | `#f59e0b` | 警告 |
| `--color-info` | `#6366f1` | 資訊 |
| `--color-accent` | `#a89cc8` | 輔助強調色 |

### 文字
| 變數 | 用途 |
|---|---|
| `--text-primary` | 主要內容文字 |
| `--text-secondary` | 次要文字、label |
| `--text-muted` | 提示文字、佔位符 |
| `--text-disabled` | 禁用狀態文字 |

### 面板/輸入框
| 變數 | 用途 |
|---|---|
| `--panel-bg` | 面板背景（半透明） |
| `--panel-bg-hover` | 面板 hover 背景 |
| `--panel-bg-active` | active/selected 狀態 |
| `--panel-border` | 面板邊框 |
| `--panel-border-hover` | 面板 hover 邊框 |
| `--input-bg` | 輸入框背景 |
| `--input-bg-focus` | 輸入框 focus 背景 |
| `--input-border` | 輸入框邊框 |
| `--input-border-focus` | 輸入框 focus 邊框 |

---

## 3. 間距規範

使用 `rem` 為單位，基準 `1rem = 15px`：

| 用途 | 值 |
|---|---|
| 元素間距（`gap`）— 緊湊 | `0.25rem` (4px) |
| 元素間距（`gap`）— 標準 | `0.5rem` (8px) |
| 元素間距（`gap`）— 寬鬆 | `1rem` (16px) |
| form-group 內部 gap | `0.5rem` |
| function-settings gap | `1rem` |
| 標準 input padding | `0.5rem 0.75rem` |
| 小型 input padding | `0.375rem 0.75rem` |

---

## 4. 圓角規範

| 用途 | 值 |
|---|---|
| 大型容器（主面板、卡片） | `12px` |
| 按鈕、卡片、大型元素 | `8px` |
| input、select、Badge、Tag | `6px` |
| 圓形（icon button、slider grip） | `50%` |

---

## 5. 字型大小規範

| 用途 | 值 |
|---|---|
| 正文（body 預設） | `15px` |
| 標題（settings-title） | `1rem` / `font-weight: 500` |
| 標準文字、label、input | `0.85rem` |
| sub-label、小型 badge | `0.8rem` |
| 次要說明文字 | `0.78rem` |
| 提示文字 hint | `0.75rem` |
| 微型說明（ticks、hint-small） | `0.72rem` |
| Badge | `0.6rem` / `font-weight: 600` |

---

## 6. 動畫與過渡

- 互動回饋（hover、active）：`transition: all 0.15s ease`
- 狀態切換（顯示/隱藏元素）：`transition: opacity 0.2s ease`
- 主題切換：`transition: background 0.3s ease, color 0.3s ease`
- 主畫面進場：`animation: fadeIn 0.4s ease`
- 禁止使用超過 `0.4s` 的過渡動畫（操作回饋應即時）

---

## 7. 共用樣式類別

共用樣式定義於 `src/styles/tool-panels-shared.scss`，所有 panel 透過 `@use '@/styles/tool-panels-shared'` 引入。

### 容器

```html
<!-- 所有 tool panel 的根容器，統一使用此 class -->
<div class="function-settings">...</div>
```

### 標題

```html
<h6 class="settings-title">
  <i class="bi bi-xxx me-2"></i>功能名稱
</h6>
```

### 表單組

```html
<div class="form-group">
  <label>欄位名稱</label>
  <!-- input / select / toggle -->
  <small class="form-hint">說明文字</small>
</div>
```

### 輸入框

```html
<input class="form-input" type="text" placeholder="..." />
<textarea class="form-input" rows="4"></textarea>
```

### 檔案路徑選擇

**Tool panels**（`function-settings` 容器內）：使用 `.file-select` div

```html
<div class="file-select" @click="selectFile">
  <span class="file-select-path">{{ displayPath }}</span>
  <i class="bi bi-folder2-open"></i>
</div>
```

**Settings Tab**（`settings-shared` 環境）：使用 `btn-secondary path-btn` button，路徑文字置左、icon 置右、滿版寬

```html
<button class="btn-secondary path-btn" @click="selectDir">
  <span class="path-text">{{ dir }}</span>
  <i class="bi bi-folder2-open"></i>
</button>
```

```scss
// scoped style
.path-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  .path-text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
  }
  i { flex-shrink: 0; }
}
```

---

## 8. 按鈕規範

按鈕類別依使用場景分為兩套來源：

| 場景 | 引入方式 | 寬度行為 |
|---|---|---|
| Tool panels（`function-settings` 容器內） | `@use '@/styles/tool-panels-shared'` | 自動滿版寬 |
| Settings 頁面（`setting-item` 容器內） | `@use '@/styles/settings-shared'` | 縮為內容寬（`inline-flex`） |

兩套共用相同 class 名稱，視覺語言一致；差異僅在寬度。

### 次要操作按鈕（重設、清除、瀏覽、一般動作）

```html
<button class="btn-secondary" @click="...">
  <i class="bi bi-arrow-counterclockwise"></i>重設
</button>
```

### 主要 CTA 按鈕（安裝、首次啟用）

```html
<button class="btn-primary" :disabled="isLoading" @click="...">
  <i class="bi bi-download"></i>安裝功能
</button>
```

### 成功狀態按鈕（僅限 Settings，如重啟提示）

```html
<button class="btn-success" @click="...">
  <i class="bi bi-arrow-counterclockwise"></i>立即重啟
</button>
```

> 僅在 `settings-shared` 中定義，tool panels 不使用。

### 選擇型按鈕群（倍率、模式切換）

```html
<div class="btn-choice-group">
  <button
    v-for="v in [1, 2, 4]"
    :key="v"
    class="btn-choice"
    :class="{ 'is-active': selected === v }"
    @click="selected = v"
  >{{ v }}x</button>
</div>
```

> ⚠️ active class 一律使用 `is-active`，不使用 `active`（適用所有互動元素）

### 執行按鈕（ToolLayout 底部 CTA）

由 ToolLayout 統一管理，各 View 透過 `:execute-disabled`、`:execute-loading`、`execute-label`、`@execute` props 控制。**禁止在 settings slot 內放第二個執行按鈕。**

### Toolbar 按鈕（預覽區浮層按鈕）
- 尺寸：`32×32px`
- 預設背景：`rgba(0, 0, 0, 0.4)`，`opacity: 0.7`
- hover：`opacity: 1`
- Tooltip：使用 `data-tooltip` + CSS `::after`（同 MainSidebar 的 nav-btn 樣式）
- 危險操作（刪除）hover：`background: rgba(220, 53, 69, 0.8)`
- Disabled：`opacity: 0.3; cursor: not-allowed; pointer-events: none`

---

## 9. Toggle 開關

**一律使用 `AppToggle` 組件**，不自行實作。

```html
<AppToggle v-model="someBoolean">顯示說明文字</AppToggle>
```

---

## 10. Range 滑桿

使用 `AppRange` 組件，搭配以下輔助元素：

```html
<div class="form-group">
  <label>
    放大倍率
    <span class="param-value">{{ value }}x</span>  <!-- 數值顯示 -->
  </label>
  <AppRange v-model="value" :min="2" :max="4" :step="1" />
  <div class="range-ticks">                          <!-- 刻度標籤 -->
    <span>2x</span><span>3x</span><span>4x</span>
  </div>
</div>
```

---

## 11. Info / Alert Box

取代各 component 自行定義的 warn-box、error-msg、usage-hint。

### 資訊（info）

```html
<div class="info-box info-box--info">
  <i class="bi bi-brush"></i>
  <span>操作說明文字</span>
</div>
```

### 警告（warn）—— 含操作按鈕

```html
<div class="info-box info-box--warn">
  <i class="bi bi-exclamation-triangle"></i>
  <div class="info-box-body">
    <span>警告說明文字</span>
    <button class="info-box-action" @click="...">前往設定</button>
  </div>
</div>
```

### 錯誤（error）

```html
<div class="info-box info-box--error">
  <i class="bi bi-exclamation-circle"></i>
  <span>{{ errorMessage }}</span>
</div>
```

---

## 12. 次級參數區塊

用於 toggle 展開後的子參數（如超解析的人臉修復設定）：

```html
<div v-if="showAdvanced" class="sub-params">
  <label class="sub-label">子參數名稱</label>
  <AppSelect ... />
  <!-- 其他子參數 -->
</div>
```

`sub-params` 內也可以放 `form-group`（含 `AppRange`）或 `option-row`（toggle + hint）：

```html
<div v-if="showAdvanced" class="sub-params">
  <!-- Range 參數 -->
  <div class="form-group">
    <label class="sub-label">
      參數名稱 <span class="param-value">{{ value }}</span>
    </label>
    <AppRange v-model="value" :min="0" :max="100" :step="1" />
    <small class="form-hint">說明文字</small>
  </div>

  <!-- Toggle + 說明 -->
  <div class="option-row">
    <AppToggle v-model="flag">選項說明</AppToggle>
    <span class="form-hint">補充說明</span>
  </div>
</div>
```

> `.option-row` 是 scoped style，宣告為 `display: flex; flex-direction: column; gap: 0.25rem`

---

## 13. 尺寸輸入

用於寬 × 高等成對數值輸入：

```html
<div class="form-group size-inputs">
  <div class="size-input-group">
    <label>寬度</label>
    <input class="form-input" type="number" v-model="width" />
  </div>
  <span class="size-separator">×</span>
  <div class="size-input-group">
    <label>高度</label>
    <input class="form-input" type="number" v-model="height" />
  </div>
</div>
```

---

## 14. Label 輔助文字

用於 label 旁的灰色次要說明（如「選填」）：

```html
<label>專有名詞字典 <span class="label-hint">（選填）</span></label>
```

> `.label-hint` 是 scoped style：`font-size: 0.78rem; color: var(--text-muted); font-weight: 400`

---

## 15. Checkbox

優先使用 `AppToggle`。若需要 checkbox 語意（多選清單），使用：

```html
<label class="checkbox-label">
  <input type="checkbox" v-model="value" />
  <span>選項文字</span>
</label>
```

---

## 16. 共用元件（`src/components/common/`）

| 元件 | 用途 |
|---|---|
| `AppSelect` | 所有下拉選單，支援 badge、desc |
| `AppToggle` | 所有開關，支援 disabled |
| `AppRange` | 所有滑桿 |
| `AppMediaInfoBar` | 媒體資訊列 |
| `AppUploadZone` | 拖曳上傳區域 |
| `AppButtonGroup` | 分段選擇按鈕（如放大倍率 2x/3x/4x） |
| `AppToast` | 所有 Toast 通知（透過 `useToast` composable） |

---

## 17. Panel 結構範本

```vue
<script setup lang="ts">
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

const { submitTask, isProcessing } = useSubmitTask()
const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-xxx me-2"></i>XX設定</h6>

    <!-- 工具說明（必填）：一句話描述此工具的用途 -->
    <p class="form-hint">簡短說明這個工具的功能與使用情境。</p>

    <!-- info-box（如有警告/錯誤，放在說明之後） -->

    <!-- form-group × N -->
    <div class="form-group">
      <label>...</label>
      <!-- AppSelect / AppToggle / AppRange / input -->
      <small class="form-hint">...</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';  /* 非 scoped，引入共用樣式 */
</style>

<!-- scoped style 只寫此 component 獨有的版面邏輯 -->
```

### Panel 標題命名規則

右側設定面板的標題一律使用「**XX設定**」格式，XX 對應左側 tab 的名稱。

| Tab 名稱 | settings-title |
|---|---|
| 轉檔 | 轉檔設定 |
| 剪輯 | 剪輯設定 |
| 字幕 | 字幕設定 |
| 物件移除 | 物件移除設定 |
| 文字辨識 | 文字辨識設定 |

### 輸出路徑原則

| 情境 | 方式 | 說明 |
|---|---|---|
| **產出獨立新檔案**（字幕、逐字稿、OCR、PDF 轉換、分割） | 輸出路徑選擇 | 使用者設定完可直接執行，不需留在畫面等待 |
| **對原始媒體的處理**（轉檔、剪輯、去背、濾鏡、壓縮等） | 下載按鈕 | 結果顯示在 preview 區，使用者確認後下載 |

### Preview 原則

| 情境 | 是否需要 Preview |
|---|---|
| 所有圖片工具 | ✅ 需要（結果需視覺確認，或互動式操作如裁切、物件移除） |
| 影片剪輯、影片字幕 | ✅ 需要（需對著影片設定時間點或確認字幕） |
| 影片轉檔、所有音訊工具、所有文件工具 | ❌ 不需要（純參數設定，執行後等待下載或指定輸出路徑） |

---

## 18. 工具頁面架構（ToolLayout 模式）

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
3. **設定面板樣式**：使用 `tool-panels-shared.scss` 提供的 class，不在各 View 重複定義

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

## 19. 選中狀態（Active Indicator）

**所有 sidebar/nav 類的選中狀態使用左側 accent bar，禁止僅用背景色區分（與 hover 重疊）。**

```scss
// 通用 active 樣式
&.is-active {
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

## 20. 通知系統

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

## 21. 數字與單位格式

| 資料類型 | 格式 | 範例 |
|---------|------|------|
| 解析度 | `W × H`（Unicode 乘號）| `1920 × 1080` |
| 時間長度 | `m:ss` / `h:mm:ss` | `3:45`、`1:23:45` |
| 檔案大小 | 自動單位（B / KB / MB / GB）| `1.2 MB` |
| 位元率 | 自動單位（bps / Kbps / Mbps）| `5.2 Mbps` |
| 進度 | 百分比，無小數 | `42%` |
| 縮放比例 | 百分比，無小數 | `150%` |

---

## 22. Settings Tab 元件規範

設定頁各 Tab 元件（`src/components/settings/`）使用獨立共用樣式，**不引入** `tool-panels-shared`。

### 引入方式

```vue
<style lang="scss">
@use '@/styles/settings-shared';  /* 非 scoped */
</style>
```

### 可用共用 class

| Class | 用途 |
|---|---|
| `section-title` | 區塊標題（h6） |
| `section-subtitle` | 欄位副標題（label） |
| `setting-item` | 每個設定項目的容器（margin-bottom） |
| `btn-primary` | 主要按鈕（`inline-flex`，內容寬） |
| `btn-secondary` | 次要按鈕（`inline-flex`，內容寬，底色同 input） |
| `btn-success` | 成功狀態按鈕（綠色，用於重啟提示等） |
| `form-input` | 標準輸入框（含 readonly 狀態） |
| `spinner` | 旋轉載入指示器 |

### Settings Tab 結構範本

```vue
<template>
  <h6 class="section-title">區塊標題</h6>

  <div class="setting-item">
    <label class="section-subtitle">欄位名稱</label>
    <AppSelect v-model="value" :options="options" size="sm" />
  </div>

  <div class="setting-item">
    <AppToggle v-model="flag">開關說明文字</AppToggle>
  </div>

  <div class="setting-item">
    <button class="btn-secondary" @click="...">
      <i class="bi bi-arrow-counterclockwise"></i> 動作
    </button>
  </div>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>
```

> ⚠️ Settings 元件同樣禁止自行實作 toggle（使用 `AppToggle`）、自訂 `form-control` 等非規範 class

---

## 23. 元件拆分原則

### 何時拆分

滿足以下任一條件應拆分：

| 條件 | 說明 |
|---|---|
| **行數 > 300** | 單一 `.vue` 超過 300 行應評估是否有可獨立的職責 |
| **多重職責** | 同一檔案處理兩個以上不相關功能（例：AI 環境安裝 + 模型下載） |
| **可複用邏輯** | 渲染邏輯、拖拽行為、Markdown 解析等可跨元件共用的區塊 |
| **深層嵌套** | template 中有可獨立成 component 的大型 v-if 展開區塊 |

### 拆分命名慣例

| 類型 | 命名規則 | 範例 |
|---|---|---|
| 功能獨立的 UI 區塊 | `XxxPanel.vue` | `AiEnvironmentPanel.vue` |
| Layout 功能元件 | 描述行為 | `ComparisonSlider.vue` |
| 可複用工具元件 | 放 `common/` | `MarkdownRenderer.vue` |
| Overlay / Modal | 描述用途 | `UnsupportedFileOverlay.vue` |
| 子設定區塊 | `XxxSettings.vue` 或 `XxxOptions.vue` | `WhisperAdvancedSettings.vue` |

### 父子通訊模式

**子元件狀態由父層讀取（submit 時聚合）→ 使用 `defineExpose`**

```ts
// 子元件
defineExpose({ valueA, valueB, parseData })

// 父元件
const childRef = ref<InstanceType<typeof ChildComponent> | null>(null)

// 在 submit 函數中讀取
const result = childRef.value?.valueA
```

**子元件狀態需即時反映到父層 → 使用 emit**

```ts
// 子元件
const emit = defineEmits<{ 'update:value': [val: string] }>()
watch(value, v => emit('update:value', v))

// 父元件
<ChildComponent @update:value="parentValue = $event" />
```

> ⚠️ **禁止** 在父層 `computed()` 中存取 `childRef.value?.someRef?.value` — Vue 不會追蹤跨元件的 ref 存取，computed 不會更新

### 樣式拆分規則

- 拆出的子元件各自引入 `@use '@/styles/tool-panels-shared'`（非 scoped）
- 子元件的 scoped style 只保留該元件**獨有**的版面邏輯
- 拆分後原始檔的 scoped style 若已全數移出，刪除空的 `<style>` 區塊

### 已拆分的元件對照表

| 原始檔 | 拆出元件 | 職責 |
|---|---|---|
| `ToolLayout.vue` | `ComparisonSlider.vue` | Slider 拖拽比對邏輯 |
| `ToolLayout.vue` | `UnsupportedFileOverlay.vue` | 不支援格式提示 overlay |
| `SettingsModels.vue` | `AiEnvironmentPanel.vue` | AI 核心模組安裝/狀態 |
| `SettingsModels.vue` | `ModelDownloadManager.vue` | 模型下載、進度輪詢 |
| `SubtitlePanel.vue` | `WhisperAdvancedSettings.vue` | 進階分句參數（VAD、時間戳）|
| `SubtitlePanel.vue` | `TranslationOptionsPanel.vue` | 翻譯設定（語言、模型、字典）|
| `OcrResultModal.vue` | `MarkdownRenderer.vue` | Markdown / 表格渲染（`common/`）|

---

## 24. 禁止事項

- ❌ 不得在 scoped style 中重新定義 `.form-group`、`.form-input`、`.form-hint`
- ❌ 不得自行實作 toggle switch（一律使用 `AppToggle`，包含 settings 頁面）
- ❌ 不得自行實作 range slider（一律使用 `AppRange`）
- ❌ 不得使用非規範的 active class 名稱（一律使用 `is-active`，不使用 `active`）
- ❌ 不得在 panel 中自行定義 `.file-select`、`.warn-box`、`.error-msg`、`.value-badge`、`.mode-btn` 等已有共用版本的樣式
- ❌ 不得使用 `linear-gradient` 作為按鈕背景（使用 `--color-primary`）
- ❌ Tool panel container class 一律使用 `function-settings`，不得使用 `ocr-panel`、`split-panel` 等自訂名稱
- ❌ 不得在 scoped style 中重複定義 `.btn-primary`、`.btn-secondary` 的 `background`、`color`、`border`、`cursor`（僅可新增 modifier 覆蓋尺寸/形狀）
- ❌ Settings 元件不得自訂按鈕 class（`.browse-btn`、`.restart-btn` 等），一律使用 `btn-secondary` / `btn-primary` / `btn-success`
- ❌ Settings 元件不得使用 `form-control`，一律使用 `form-input`
- ❌ 禁止寫死 hex 色值（`#ffffff`、`rgba(...)` 等），必須使用 CSS 變數（主題切換會失效）
- ❌ 禁止在 settings slot 內放執行按鈕（統一走 ToolLayout 底部）
- ❌ 禁止使用 `alert()`、`confirm()`（使用 Toast 或 Modal）
- ❌ 禁止對未完成功能顯示正常可用的 UI（必須加 `comingSoon` 標記）
- ❌ 禁止使用超過 `0.4s` 的過渡動畫
