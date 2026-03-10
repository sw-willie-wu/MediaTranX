# MediaTranX Frontend Design System

> 所有前端 UI 元件必須遵循本規範。新增功能時先查閱此文件，不得在 component scoped style 中重複定義已有的共用樣式。

---

## 設計原則

- **一致性**：相同用途的 UI 元素使用相同的樣式 class，不得各自實作
- **規範優先**：先找共用 class，找不到再向 `tool-panels-shared.scss` 新增，最後才寫 scoped style
- **最小化 scoped style**：scoped style 只用於該 component 獨有的版面邏輯，不重複定義顏色/間距/邊框

---

## Design Tokens（CSS 變數）

定義於 `src/assets/base.css`。

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
| `--panel-bg` | 面板背景 |
| `--panel-bg-hover` | 面板 hover 背景 |
| `--panel-border` | 面板邊框 |
| `--panel-border-hover` | 面板 hover 邊框 |
| `--input-bg` | 輸入框背景 |
| `--input-bg-focus` | 輸入框 focus 背景 |
| `--input-border` | 輸入框邊框 |
| `--input-border-focus` | 輸入框 focus 邊框 |

---

## 間距規範

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

## 圓角規範

| 用途 | 值 |
|---|---|
| input、select、小型元素 | `6px` |
| 按鈕、卡片、大型元素 | `8px` |
| 大型容器 | `12px` |
| 圓形（icon button） | `50%` |

---

## 字型大小規範

| 用途 | 值 |
|---|---|
| 微型說明（ticks、hint-small） | `0.72rem` |
| 提示文字 hint | `0.75rem` |
| 次要說明文字 | `0.78rem` |
| sub-label、小型 badge | `0.8rem` |
| 標準文字、label、input | `0.85rem` |
| 標題（settings-title） | `1rem` |

---

## 共用樣式類別

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

## 按鈕規範

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

---

## Toggle 開關

**一律使用 `AppToggle` 組件**，不自行實作。

```html
<AppToggle v-model="someBoolean">顯示說明文字</AppToggle>
```

---

## Range 滑桿

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

## Info / Alert Box

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

## 次級參數區塊

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

## 尺寸輸入

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

## Label 輔助文字

用於 label 旁的灰色次要說明（如「選填」）：

```html
<label>專有名詞字典 <span class="label-hint">（選填）</span></label>
```

> `.label-hint` 是 scoped style：`font-size: 0.78rem; color: var(--text-muted); font-weight: 400`

---

## Checkbox

優先使用 `AppToggle`。若需要 checkbox 語意（多選清單），使用：

```html
<label class="checkbox-label">
  <input type="checkbox" v-model="value" />
  <span>選項文字</span>
</label>
```

---

## 共用元件（`src/components/common/`）

| 元件 | 用途 |
|---|---|
| `AppSelect` | 所有下拉選單，支援 badge、desc |
| `AppToggle` | 所有開關，支援 disabled |
| `AppRange` | 所有滑桿 |
| `AppMediaInfoBar` | 媒體資訊列 |
| `AppUploadZone` | 拖曳上傳區域 |

---

## Panel 結構範本

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

## Settings Tab 元件規範

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

---

## 元件拆分原則

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

## 禁止事項

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
