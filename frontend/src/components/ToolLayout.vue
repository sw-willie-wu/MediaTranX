<script setup lang="ts">
import { ref, computed, watch, onActivated, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppUploadZone from '@/components/common/AppUploadZone.vue'
import ComparisonSlider from '@/components/ComparisonSlider.vue'
import UnsupportedFileOverlay from '@/components/UnsupportedFileOverlay.vue'
import { useFilesStore } from '@/stores/files'
import { useResizableLayout } from '@/composables/useResizableLayout'
import { useTitlebar } from '@/composables/useTitlebar'
import { detectMediaType, getToolPath, type ToolType } from '@/utils/mediaType'
import { createLogger } from '@/utils/logger'
import { usePasteUpload } from '@/composables/usePasteUpload'
import { useUrlDownload } from '@/composables/useUrlDownload'

const { t } = useI18n()
const log = createLogger('ToolLayout')
const { sidebarWidth, settingsWidth, startResize } = useResizableLayout()
const { setFileName, clearFileName } = useTitlebar()

interface SubFunction {
  id: string
  name: string
  icon: string
  comingSoon?: boolean
  group?: string
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
  isComparing?: boolean
  executeDisabled?: boolean
  executeLoading?: boolean
  executeLabel?: string
  hideExecute?: boolean
  showFilmstrip?: boolean
  collectionSize?: number
  originalPreviewUrl?: string | null
  functionsLocked?: boolean
  activeFileName?: string
}>(), {
  uploadIcon: 'bi-cloud-arrow-up-fill',
  uploadAccept: '*',
  resultPreviewUrl: null,
  showFilmstrip: false,
})

// Group functions by group label (undefined group = ungrouped)
const groupedFunctions = computed(() => {
  const groups: Array<{ label: string | null; items: SubFunction[] }> = []
  let currentGroup: string | null | undefined = '__INIT__'
  for (const fn of props.subFunctions) {
    if (fn.group !== currentGroup) {
      groups.push({ label: fn.group ?? null, items: [] })
      currentGroup = fn.group
    }
    groups[groups.length - 1].items.push(fn)
  }
  return groups
})
const hasGroups = computed(() => groupedFunctions.value.some(g => g.label !== null))

const effectiveUploadLabel = computed(() => props.uploadLabel ?? t('common.drop_files'))
const effectiveUploadHint = computed(() => props.uploadHint ?? t('common.drop_hint'))
const effectiveExecuteLabel = computed(() => props.executeLabel ?? t('common.execute'))

// Execute success flash
const executeSuccess = ref(false)
let successTimer: ReturnType<typeof setTimeout> | null = null

watch(() => props.executeLoading, (loading, wasLoading) => {
  if (wasLoading && !loading && props.hasResult) {
    executeSuccess.value = true
    if (successTimer) clearTimeout(successTimer)
    successTimer = setTimeout(() => { executeSuccess.value = false }, 1500)
  }
})

const emit = defineEmits<{
  (e: 'select-function', id: string): void
  (e: 'execute'): void
  (e: 'file', file: File, sourceDir?: string): void
  (e: 'files', files: File[]): void
  (e: 'existing-files', refs: import('@/stores/files').PendingResultRef[]): void
  (e: 'remove-file'): void
  (e: 'clear-selection'): void
}>()

const currentSubFunction = computed(() =>
  props.subFunctions.find(fn => fn.id === props.currentFunction)
)
const isCurrentComingSoon = computed(() => currentSubFunction.value?.comingSoon ?? false)

const router = useRouter()
const filesStore = useFilesStore()

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

// Sync titlebar filename — filmstrip mode uses prop, single-file uses internal state
watch(
  () => props.activeFileName ?? currentFile.value?.name ?? '',
  (name) => { if (name) { setFileName(name) } else { clearFileName() } },
  { immediate: true },
)

// When collection is cleared externally (all entries removed), reset internal state
watch(
  () => props.collectionSize,
  (size) => {
    if (props.showFilmstrip && (size ?? 0) === 0) {
      if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
      currentFile.value = null
      previewUrl.value = null
      clearFileName()
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
  setFileName(file.name)
  emit('file', file, sourceDir)
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

const urlDownload = useUrlDownload()

// 貼上 = 拖曳的另一個入口:單檔走型別驗證路徑,多檔走 filmstrip 批次。
// 貼上內容無 sourceDir(走 HTTP upload),與拖曳語意一致。
// URL 偵測只在 video tool 啟用,其他 tool 傳 undefined 跳過。
usePasteUpload((files) => {
  if (files.length === 1) {
    handleUploadFile(files[0])
  } else {
    handleUploadFiles(files)
  }
}, props.acceptType === 'video' ? (url) => urlDownload.handlePastedUrl(url) : undefined)

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
  // Single pending file
  const pending = filesStore.consumePendingFile()
  if (pending) setFile(pending.file, pending.sourceDir)
  // Batch pending files (cross-tool open with multi-select)
  const many = filesStore.consumePendingFiles()
  if (many.length > 0) emit('files', many)
  // Batch pending results (open-in-tool by reference, no upload)
  const manyResults = filesStore.consumePendingResults()
  if (manyResults.length > 0) emit('existing-files', manyResults)
})

onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  if (unsupportedTimer) clearTimeout(unsupportedTimer)
  clearFileName()
})
</script>

<template>
  <div class="tool-layout">
    <!-- 左側：子功能列表 -->
    <aside class="function-sidebar" :style="{ width: sidebarWidth + 'px', minWidth: sidebarWidth + 'px' }" @click.self="emit('clear-selection')">
      <div class="function-list">
        <template v-for="(group, gi) in groupedFunctions" :key="gi">
          <div v-if="group.label && hasGroups" class="function-group-label">{{ group.label }}</div>
          <button
            v-for="fn in group.items"
            :key="fn.id"
            class="function-item"
            :class="{ 'is-active': currentFunction === fn.id, 'coming-soon': fn.comingSoon, 'is-locked': functionsLocked && currentFunction !== fn.id }"
            :disabled="functionsLocked && currentFunction !== fn.id"
            @click="emit('select-function', fn.id)"
          >
            <i :class="['bi', fn.icon]"></i>
            <span>{{ fn.name }}</span>
            <span v-if="fn.comingSoon" class="coming-badge">{{ $t('common.coming_soon') }}</span>
          </button>
        </template>
      </div>
    </aside>

    <div class="resize-handle" @mousedown="startResize('sidebar', $event)" @dblclick="sidebarWidth = 220"></div>

    <!-- 中間：預覽區域 -->
    <main class="preview-area" :class="{ 'is-drag-over': isDragOver && hasFile }">

      <!-- 預覽內容 -->
      <div
        class="preview-content"
        :class="{ 'has-file': hasFile }"
        @dragover="handleDragOver"
        @dragleave="handleDragLeave"
        @drop.capture="isDragOver = false"
        @drop="handleDrop"
        @click.self="emit('clear-selection')"
      >
        <!-- 不支援類型 overlay -->
        <UnsupportedFileOverlay
          :visible="showUnsupported"
          :target="unsupportedTarget"
          @dismiss="dismissUnsupported"
          @go-to-tool="goToTool"
        />

        <AppUploadZone
          v-if="!hasFile"
          :icon="uploadIcon"
          :label="effectiveUploadLabel"
          :hint="effectiveUploadHint"
          :accept="uploadAccept"
          :multiple="showFilmstrip"
          @file="handleUploadFile"
          @files="handleUploadFiles"
        />

        <!-- 有檔案：比對模式 / 預覽 -->
        <div v-else class="preview-slot-wrapper">
          <ComparisonSlider
            v-if="isComparing && resultPreviewUrl"
            :original-url="props.originalPreviewUrl ?? previewUrl!"
            :result-url="resultPreviewUrl"
            :result-meta="props.resultMeta"
          />
          <slot
            v-else
            name="preview"
            :file="currentFile!"
            :previewUrl="previewUrl!"
          >
            <div class="preview-placeholder">
              <i class="bi bi-image"></i>
              <p>{{ $t('common.select_or_drop') }}</p>
            </div>
          </slot>
        </div>

      </div>

      <!-- 資訊列：filmstrip 模式（preview-area flex child，在 filmstrip 上方） -->
      <div v-if="showFilmstrip && hasFile" class="preview-info-bar preview-info-bar--overlay">
        <slot name="info-bar" />
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

    <div class="resize-handle" @mousedown="startResize('settings', $event)" @dblclick="settingsWidth = 272"></div>

    <!-- 右側：設定面板 -->
    <aside class="settings-panel" :style="{ width: settingsWidth + 'px', minWidth: settingsWidth + 'px' }">
      <div class="settings-content">
        <slot name="settings">
          <p class="text-muted">{{ $t('common.select_function') }}</p>
        </slot>
      </div>

      <!-- 執行按鈕 -->
      <div v-if="!hideExecute && !isCurrentComingSoon" class="execute-section">
        <button
          class="execute-btn"
          :class="{ 'is-success': executeSuccess }"
          :disabled="executeDisabled || executeLoading"
          @click="emit('execute')"
        >
          <span v-if="executeLoading" class="spinner-border spinner-border-sm me-2"></span>
          <i v-else-if="executeSuccess" class="bi bi-check-lg me-2"></i>
          <i v-else class="bi bi-play-fill me-2"></i>
          {{ executeLoading ? $t('common.processing') : executeSuccess ? $t('common.completed') : effectiveExecuteLabel }}
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
  padding: 0.5rem 1rem 1rem 0;
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

.function-group-label {
  padding: 0.5rem 0.75rem 0.15rem;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);

  &:not(:first-child) {
    margin-top: 0.35rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--panel-border);
  }
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
  scrollbar-gutter: stable;
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

  // Overlay mode (showFilmstrip = true) — inline at top of filmstrip slot
  &--overlay {
    min-height: unset;
    padding: 0.35rem 0.9rem;
    border-top: none;
    flex-shrink: 0;
    justify-content: center;

    :deep(.media-info-bar) {
      border-top: none;
      padding: 0;
      justify-content: center;
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

  &.is-success {
    background: var(--color-success);
    &:hover:not(:disabled) {
      background: var(--color-success-hover);
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
    }
  }
}

.text-muted { color: var(--text-muted); }

// ── Fade transition ───────────────────────────────────────────
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.preview-slot-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}
</style>
