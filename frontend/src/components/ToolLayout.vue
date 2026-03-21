<script setup lang="ts">
import { ref, computed, watch, onActivated, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import AppUploadZone from '@/components/common/AppUploadZone.vue'
import ComparisonSlider from '@/components/ComparisonSlider.vue'
import UnsupportedFileOverlay from '@/components/UnsupportedFileOverlay.vue'
import { useFilesStore } from '@/stores/files'
import { useResizableLayout } from '@/composables/useResizableLayout'
import { detectMediaType, getToolPath, type ToolType } from '@/utils/mediaType'
import { createLogger } from '@/utils/logger'

const log = createLogger('ToolLayout')
const { sidebarWidth, settingsWidth, startResize } = useResizableLayout()

interface SubFunction {
  id: string
  name: string
  icon: string
  comingSoon?: boolean
}

const props = withDefaults(defineProps<{
  title: string
  subFunctions: SubFunction[]
  currentFunction?: string
  acceptType?: ToolType
  uploadIcon?: string
  uploadLabel?: string
  uploadHint?: string
  uploadAccept?: string
  hasResult?: boolean
  resultPreviewUrl?: string | null
  resultMeta?: Record<string, unknown>
  canGoBack?: boolean
  executeDisabled?: boolean
  executeLoading?: boolean
  executeLabel?: string
  hideExecute?: boolean
  hidePreviewTabs?: boolean
  showFilmstrip?: boolean
  collectionSize?: number
  originalPreviewUrl?: string | null
  functionsLocked?: boolean
}>(), {
  uploadIcon: 'bi-cloud-arrow-up-fill',
  uploadLabel: '拖曳檔案到這裡',
  uploadHint: '或點擊選擇檔案',
  uploadAccept: '*',
  executeLabel: '開始執行',
  resultPreviewUrl: null,
  showFilmstrip: false,
})

const emit = defineEmits<{
  (e: 'select-function', id: string): void
  (e: 'execute'): void
  (e: 'file', file: File, sourceDir?: string): void
  (e: 'files', files: File[]): void
  (e: 'remove-file'): void
  (e: 'download'): void
  (e: 'go-back'): void
}>()

const currentSubFunction = computed(() =>
  props.subFunctions.find(fn => fn.id === props.currentFunction)
)
const isCurrentComingSoon = computed(() => currentSubFunction.value?.comingSoon ?? false)

const router = useRouter()
const filesStore = useFilesStore()

// 預覽模式
type PreviewMode = 'original' | 'result' | 'compare'
const previewMode = ref<PreviewMode>('original')
const canShowResult = computed(() => props.hasResult)

// Slider 比對模式
const isComparing = ref(false)

function toggleCompare() {
  isComparing.value = !isComparing.value
}

// 內部檔案管理
const currentFile = ref<File | null>(null)
const previewUrl = ref<string | null>(null)
// In filmstrip mode: use collectionSize from parent OR currentFile as immediate fallback
// (addEntry is async, so collectionSize lags behind the synchronous setFile call)
const hasFile = computed(() =>
  props.showFilmstrip
    ? (props.collectionSize ?? 0) > 0 || !!currentFile.value
    : !!currentFile.value
)

// When collection is cleared externally (all entries removed), reset internal state
watch(
  () => props.collectionSize,
  (size) => {
    if (props.showFilmstrip && (size ?? 0) === 0) {
      if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
      currentFile.value = null
      previewUrl.value = null
    }
  },
)

// 不支援類型 overlay
const showUnsupported = ref(false)
const unsupportedTarget = ref<ToolType | null>(null)
let unsupportedTimer: ReturnType<typeof setTimeout> | null = null

// 拖曳 hover 狀態
const isDragOver = ref(false)

function setFile(file: File, sourceDir?: string) {
  log.info('setFile', { fileName: file.name, size: file.size, sourceDir })
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  currentFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  previewMode.value = 'original'
  emit('file', file, sourceDir)
}

function removeFile() {
  log.info('removeFile')
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  currentFile.value = null
  previewUrl.value = null
  previewMode.value = 'original'
  isComparing.value = false
  emit('remove-file')
}

function handleUploadFile(file: File, sourceDir?: string) {
  if (props.acceptType) {
    const detected = detectMediaType(file)
    if (detected && detected !== props.acceptType) {
      log.warn('unsupported file type', { fileName: file.name, detected, expected: props.acceptType })
      showUnsupportedOverlay(detected)
      return
    }
  }
  setFile(file, sourceDir)
}

function handleUploadFiles(files: File[]) {
  emit('files', files)
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  // Multi-file drop in filmstrip mode: validate type then forward all files to parent.
  // Set currentFile temporarily so the upload zone hides immediately while async addEntry runs.
  if (props.showFilmstrip && files.length > 1) {
    const validFiles = props.acceptType
      ? Array.from(files).filter(f => {
          const detected = detectMediaType(f)
          return detected === props.acceptType
        })
      : Array.from(files)
    if (validFiles.length === 0) { showUnsupportedOverlay(null); return }
    currentFile.value = validFiles[0]
    emit('files', validFiles)
    return
  }

  const file = files[0]
  const sourceDir = window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined

  if (props.acceptType) {
    const detected = detectMediaType(file)
    if (detected && detected !== props.acceptType) {
      showUnsupportedOverlay(detected)
      return
    }
    if (!detected) {
      showUnsupportedOverlay(null)
      return
    }
  }

  setFile(file, sourceDir)
}

function handleDragOver(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}

function handleDragLeave() {
  isDragOver.value = false
}

function showUnsupportedOverlay(target: ToolType | null) {
  unsupportedTarget.value = target
  showUnsupported.value = true
  if (unsupportedTimer) clearTimeout(unsupportedTimer)
  unsupportedTimer = setTimeout(() => { showUnsupported.value = false }, 3000)
}

function dismissUnsupported() {
  showUnsupported.value = false
  if (unsupportedTimer) clearTimeout(unsupportedTimer)
}

function goToTool() {
  if (unsupportedTarget.value) router.push(getToolPath(unsupportedTarget.value))
  dismissUnsupported()
}

// KeepAlive: 每次 activated 時檢查 pending file
onActivated(() => {
  const pending = filesStore.consumePendingFile()
  if (pending) setFile(pending.file, pending.sourceDir)
})

onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  if (unsupportedTimer) clearTimeout(unsupportedTimer)
})
</script>

<template>
  <div class="tool-layout">
    <!-- 左側：子功能列表 -->
    <aside class="function-sidebar" :style="{ width: sidebarWidth + 'px', minWidth: sidebarWidth + 'px' }">
      <div class="function-list">
        <button
          v-for="fn in subFunctions"
          :key="fn.id"
          class="function-item"
          :class="{ 'is-active': currentFunction === fn.id, 'coming-soon': fn.comingSoon, 'is-locked': functionsLocked && currentFunction !== fn.id }"
          :disabled="functionsLocked && currentFunction !== fn.id"
          @click="emit('select-function', fn.id)"
        >
          <i :class="['bi', fn.icon]"></i>
          <span>{{ fn.name }}</span>
          <span v-if="fn.comingSoon" class="coming-badge">即將</span>
        </button>
      </div>
    </aside>

    <div class="resize-handle" @mousedown="startResize('sidebar', $event)" @dblclick="sidebarWidth = 180"></div>

    <!-- 中間：預覽區域 -->
    <main class="preview-area" :class="{ 'is-drag-over': isDragOver && hasFile }">
      <!-- 右上角直排按鈕群（有檔案才顯示） -->
      <div v-if="hasFile" class="preview-toolbar">
        <button v-if="!showFilmstrip" class="toolbar-btn remove-btn" data-tooltip="移除檔案" @click="removeFile">
          <i class="bi bi-x-lg"></i>
        </button>
        <button
          class="toolbar-btn compare-btn"
          :class="{ 'is-active': isComparing, disabled: !canShowResult }"
          :disabled="!canShowResult"
          data-tooltip="比對原圖與成果"
          @click="canShowResult && toggleCompare()"
        >
          <i class="bi bi-layout-split"></i>
        </button>
        <slot name="toolbar-extra" />
        <button
          class="toolbar-btn download-btn"
          :class="{ disabled: !canShowResult }"
          :disabled="!canShowResult"
          data-tooltip="儲存結果"
          @click="canShowResult && emit('download')"
        >
          <i class="bi bi-download"></i>
        </button>
        <button
          v-if="canGoBack"
          class="toolbar-btn back-btn"
          data-tooltip="回到上一步"
          @click="emit('go-back')"
        >
          <i class="bi bi-arrow-counterclockwise"></i>
        </button>
      </div>

      <!-- 預覽模式切換 (for non-image views) -->
      <div v-if="hasFile && !props.hidePreviewTabs" class="preview-tabs">
        <button
          class="preview-tab"
          :class="{ 'is-active': previewMode === 'original' }"
          @click="previewMode = 'original'"
        >原圖</button>
        <button
          class="preview-tab"
          :class="{ 'is-active': previewMode === 'result', disabled: !canShowResult }"
          :disabled="!canShowResult"
          @click="previewMode = 'result'"
        >成果</button>
        <button
          class="preview-tab"
          :class="{ 'is-active': previewMode === 'compare', disabled: !canShowResult }"
          :disabled="!canShowResult"
          @click="previewMode = 'compare'"
        >並排比對</button>
      </div>

      <!-- 預覽內容 -->
      <div
        class="preview-content"
        :class="{ 'has-file': hasFile }"
        @dragover="handleDragOver"
        @dragleave="handleDragLeave"
        @drop.capture="isDragOver = false"
        @drop="handleDrop"
      >
        <!-- 不支援類型 overlay -->
        <UnsupportedFileOverlay
          :visible="showUnsupported"
          :target="unsupportedTarget"
          @dismiss="dismissUnsupported"
          @go-to-tool="goToTool"
        />

        <!-- 無檔案時顯示上傳區 -->
        <AppUploadZone
          v-if="!hasFile"
          :icon="uploadIcon"
          :label="uploadLabel"
          :hint="uploadHint"
          :accept="uploadAccept"
          :multiple="showFilmstrip"
          @file="handleUploadFile"
          @files="handleUploadFiles"
        />

        <!-- Slider 比對模式 -->
        <ComparisonSlider
          v-else-if="isComparing && resultPreviewUrl"
          :original-url="props.originalPreviewUrl ?? previewUrl!"
          :result-url="resultPreviewUrl"
          :result-meta="props.resultMeta"
        />

        <!-- 有檔案時顯示預覽 slot -->
        <slot
          v-else
          name="preview"
          :file="currentFile!"
          :previewUrl="previewUrl!"
          :mode="previewMode"
        >
          <div class="preview-placeholder">
            <i class="bi bi-image"></i>
            <p>請選擇或拖曳檔案</p>
          </div>
        </slot>

        <!-- 資訊列：overlay 模式（showFilmstrip 為 true 時） -->
        <div v-if="showFilmstrip && hasFile" class="preview-info-bar preview-info-bar--overlay">
          <slot name="info-bar" />
        </div>
      </div>

      <!-- Filmstrip slot — 固定在 preview-area 底部，不參與 preview-content 的捲動 -->
      <div v-if="showFilmstrip && hasFile" class="filmstrip-slot">
        <slot name="filmstrip" />
      </div>

      <!-- 資訊列（標準模式，showFilmstrip 為 false 時，與右側 execute-section 同層對齊） -->
      <div v-if="!showFilmstrip && hasFile" class="preview-info-bar">
        <slot name="info-bar" />
      </div>
    </main>

    <div class="resize-handle" @mousedown="startResize('settings', $event)" @dblclick="settingsWidth = 320"></div>

    <!-- 右側：設定面板 -->
    <aside class="settings-panel" :style="{ width: settingsWidth + 'px', minWidth: settingsWidth + 'px' }">
      <div class="settings-content">
        <slot name="settings">
          <p class="text-muted">請選擇功能</p>
        </slot>
      </div>

      <!-- 執行按鈕 -->
      <div v-if="!hideExecute && !isCurrentComingSoon" class="execute-section">
        <button
          class="execute-btn"
          :disabled="executeDisabled"
          @click="emit('execute')"
        >
          <span v-if="executeLoading" class="spinner-border spinner-border-sm me-2"></span>
          <i v-else class="bi bi-play-fill me-2"></i>
          {{ executeLoading ? '處理中...' : executeLabel }}
        </button>
      </div>
    </aside>
  </div>
</template>

<style lang="scss">
@use '@/styles/layout-shared';
</style>

<style lang="scss" scoped>
.tool-layout {
  display: flex;
  height: calc(100vh - 40px);
  gap: 0;
  padding: 1rem;
}

// 左側子功能列表
.function-sidebar {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 1rem;
  padding-top: 0.5rem;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.function-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.function-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.7rem 1rem;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;

  i    { font-size: 1.1rem; width: 22px; }
  span { font-size: 0.9rem; }

  &:hover { color: var(--text-primary); background: var(--panel-bg-hover); }

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

  &.coming-soon { opacity: 0.5; }
  &.is-locked { opacity: 0.35; cursor: not-allowed; pointer-events: none; }
}

.coming-badge {
  margin-left: auto;
  padding: 1px 5px;
  background: var(--panel-bg-active);
  border: 1px solid var(--panel-border);
  border-radius: 4px;
  font-size: 0.65rem;
  color: var(--text-muted);
  line-height: 1.4;
  flex-shrink: 0;
}

// 中間預覽區
.preview-area {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  overflow: hidden;
}

.preview-toolbar {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.toolbar-btn,
:slotted(.toolbar-btn) {
  position: relative;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s ease;
  opacity: 0.75;

  &:hover:not(:disabled) { opacity: 1; }

  &.disabled, &:disabled { opacity: 0.25; cursor: not-allowed; }

  // Tooltip — 左側浮出
  &::after {
    content: attr(data-tooltip);
    position: absolute;
    right: calc(100% + 8px);
    top: 50%;
    transform: translateY(-50%);
    padding: 4px 10px;
    background: var(--panel-bg-active);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.78rem;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s ease;
  }

  &:hover:not(:disabled)::after { opacity: 1; }

  &.remove-btn:hover:not(:disabled) {
    background: rgba(220, 53, 69, 0.75);
    border-color: rgba(220, 53, 69, 0.5);
    color: #fff;
  }

  &.compare-btn:hover:not(:disabled),
  &.compare-btn.is-active {
    background: rgba(96, 165, 250, 0.25);
    border-color: rgba(96, 165, 250, 0.5);
    color: #60a5fa;
    opacity: 1;
  }

  &.download-btn:hover:not(:disabled) {
    background: rgba(52, 211, 153, 0.25);
    border-color: rgba(52, 211, 153, 0.5);
    color: #34d399;
  }

  &.back-btn:hover:not(:disabled) {
    background: rgba(251, 191, 36, 0.2);
    border-color: rgba(251, 191, 36, 0.4);
    color: #fbbf24;
  }
}

.preview-tabs {
  display: flex;
  gap: 0.25rem;
  padding: 0.75rem;
  border-bottom: 1px solid var(--panel-border);
}

.preview-tab {
  padding: 0.4rem 0.75rem;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover:not(.disabled) { background: var(--panel-bg-hover); color: var(--text-primary); }
  &.is-active { background: var(--panel-bg-active); color: var(--text-primary); }
  &.disabled { opacity: 0.4; cursor: not-allowed; }
}

.preview-content {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  overflow: auto;

  &.has-file {
    padding: 2.5rem;
  }
}

.preview-placeholder {
  text-align: center;
  color: var(--text-muted);

  i { font-size: 4rem; margin-bottom: 1rem; }
  p { font-size: 1rem; }
}

// 拖曳 hover（有檔案時：整個 preview-area 變色，不顯示 icon/文字）
.preview-area.is-drag-over {
  border-color: var(--drop-zone-border-hover);
  background: var(--input-bg);
  transition: border-color 0.15s ease, background 0.15s ease;
}

// Filmstrip slot container — direct flex child of preview-area, fixed at bottom
.filmstrip-slot {
  flex-shrink: 0;
  border-top: 1px solid var(--panel-border);
}

// 右側設定面板
.settings-panel {
  display: flex;
  flex-direction: column;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.settings-content {
  flex: 1;
  padding: 1rem;
  overflow-y: auto;
  color: var(--text-primary);
}

.execute-section {
  padding: 1rem;
  border-top: 1px solid var(--panel-border);
}

// Standard info bar (showFilmstrip = false)
.preview-info-bar {
  min-height: 4.85rem;
  padding: 1rem;
  border-top: 1px solid var(--panel-border);
  flex-shrink: 0;
  display: flex;
  align-items: center;

  :deep(.media-info-bar) {
    border-top: none;
    padding: 0;
  }

  // Overlay mode (showFilmstrip = true) — absolute, bottom-center of preview-content
  &--overlay {
    position: absolute;
    bottom: 0.25rem;
    left: 50%;
    transform: translateX(-50%);
    min-height: unset;
    padding: 0.35rem 0.9rem;
    border-top: none;
    z-index: 5;
    max-width: min(480px, 90%);

    :deep(.media-info-bar) {
      border-top: none;
      padding: 0;
    }
  }
}

.execute-btn {
  width: 100%;
  padding: 0.75rem 1rem;
  background: var(--color-primary);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.9rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    background: var(--color-primary-hover);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
  }

  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.text-muted { color: var(--text-muted); }
</style>
