<script setup lang="ts">
import { ref, computed, onActivated, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import AppUploadZone from '@/components/common/AppUploadZone.vue'
import { useFilesStore } from '@/stores/files'
import { detectMediaType, getToolLabel, getToolPath, type ToolType } from '@/utils/mediaType'

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
  uploadAccept?: string
  hasResult?: boolean
  resultPreviewUrl?: string | null
  canGoBack?: boolean
  executeDisabled?: boolean
  executeLoading?: boolean
  executeLabel?: string
  hideExecute?: boolean
  hidePreviewTabs?: boolean
}>(), {
  uploadIcon: 'bi-cloud-arrow-up-fill',
  uploadLabel: '拖曳檔案到這裡',
  uploadAccept: '*',
  executeLabel: '開始執行',
  resultPreviewUrl: null,
})

const emit = defineEmits<{
  (e: 'select-function', id: string): void
  (e: 'execute'): void
  (e: 'file', file: File, sourceDir?: string): void
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
const sliderPosition = ref(50)
const isDraggingSlider = ref(false)
const compareContainerRef = ref<HTMLElement | null>(null)

function toggleCompare() {
  isComparing.value = !isComparing.value
  if (isComparing.value) {
    sliderPosition.value = 50
  }
}

function startSliderDrag(e: MouseEvent | TouchEvent) {
  e.preventDefault()
  isDraggingSlider.value = true
  document.addEventListener('mousemove', onSliderDrag)
  document.addEventListener('mouseup', stopSliderDrag)
  document.addEventListener('touchmove', onSliderDrag)
  document.addEventListener('touchend', stopSliderDrag)
}

function onSliderDrag(e: MouseEvent | TouchEvent) {
  if (!isDraggingSlider.value || !compareContainerRef.value) return
  const rect = compareContainerRef.value.getBoundingClientRect()
  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const x = clientX - rect.left
  const pct = Math.max(0, Math.min(100, (x / rect.width) * 100))
  sliderPosition.value = pct
}

function stopSliderDrag() {
  isDraggingSlider.value = false
  document.removeEventListener('mousemove', onSliderDrag)
  document.removeEventListener('mouseup', stopSliderDrag)
  document.removeEventListener('touchmove', onSliderDrag)
  document.removeEventListener('touchend', stopSliderDrag)
}

// 內部檔案管理
const currentFile = ref<File | null>(null)
const previewUrl = ref<string | null>(null)
const hasFile = computed(() => !!currentFile.value)

// 不支援類型 overlay
const showUnsupported = ref(false)
const unsupportedTarget = ref<ToolType | null>(null)
let unsupportedTimer: ReturnType<typeof setTimeout> | null = null

// 拖曳 hover 狀態
const isDragOver = ref(false)

function setFile(file: File, sourceDir?: string) {
  // 釋放舊的 blob URL
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  currentFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  previewMode.value = 'original'
  emit('file', file, sourceDir)
}

function removeFile() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  currentFile.value = null
  previewUrl.value = null
  previewMode.value = 'original'
  isComparing.value = false
  sliderPosition.value = 50
  emit('remove-file')
}

function handleUploadFile(file: File, sourceDir?: string) {
  if (props.acceptType) {
    const detected = detectMediaType(file)
    if (detected && detected !== props.acceptType) {
      showUnsupportedOverlay(detected)
      return
    }
  }
  setFile(file, sourceDir)
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

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
  unsupportedTimer = setTimeout(() => {
    showUnsupported.value = false
  }, 3000)
}

function dismissUnsupported() {
  showUnsupported.value = false
  if (unsupportedTimer) clearTimeout(unsupportedTimer)
}

function goToTool() {
  if (unsupportedTarget.value) {
    router.push(getToolPath(unsupportedTarget.value))
  }
  dismissUnsupported()
}

// KeepAlive: 每次 activated 時檢查 pending file
onActivated(() => {
  const pending = filesStore.consumePendingFile()
  if (pending) {
    setFile(pending.file, pending.sourceDir)
  }
})

// 清理
onBeforeUnmount(() => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  if (unsupportedTimer) clearTimeout(unsupportedTimer)
})

function selectFunction(id: string) {
  emit('select-function', id)
}

function handleExecute() {
  emit('execute')
}
</script>

<template>
  <div class="tool-layout">
    <!-- 左側：子功能列表 -->
    <aside class="function-sidebar">
      <div class="function-list">
        <button
          v-for="fn in subFunctions"
          :key="fn.id"
          class="function-item"
          :class="{ active: currentFunction === fn.id, 'coming-soon': fn.comingSoon }"
          @click="selectFunction(fn.id)"
        >
          <i :class="['bi', fn.icon]"></i>
          <span>{{ fn.name }}</span>
          <span v-if="fn.comingSoon" class="coming-badge">即將</span>
        </button>
      </div>
    </aside>

    <!-- 中間：預覽區域 -->
    <main class="preview-area">
      <!-- 右上角直排按鈕群（有檔案才顯示） -->
      <div v-if="hasFile" class="preview-toolbar">
        <button
          class="toolbar-btn remove-btn"
          data-tooltip="移除檔案"
          @click="removeFile"
        >
          <i class="bi bi-x-lg"></i>
        </button>
        <button
          class="toolbar-btn compare-btn"
          :class="{ active: isComparing, disabled: !canShowResult }"
          :disabled="!canShowResult"
          data-tooltip="比對原圖與成果"
          @click="canShowResult && toggleCompare()"
        >
          <i class="bi bi-layout-split"></i>
        </button>
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
      <div class="preview-tabs" v-if="hasFile && !props.hidePreviewTabs">
        <button
          class="preview-tab"
          :class="{ active: previewMode === 'original' }"
          @click="previewMode = 'original'"
        >
          原圖
        </button>
        <button
          class="preview-tab"
          :class="{ active: previewMode === 'result', disabled: !canShowResult }"
          :disabled="!canShowResult"
          @click="previewMode = 'result'"
        >
          成果
        </button>
        <button
          class="preview-tab"
          :class="{ active: previewMode === 'compare', disabled: !canShowResult }"
          :disabled="!canShowResult"
          @click="previewMode = 'compare'"
        >
          並排比對
        </button>
      </div>

      <!-- 預覽內容 -->
      <div
        class="preview-content"
        @dragover="handleDragOver"
        @dragleave="handleDragLeave"
        @drop="handleDrop"
      >
        <!-- 不支援類型 overlay -->
        <Transition name="overlay-fade">
          <div v-if="showUnsupported" class="unsupported-overlay" @click.self="dismissUnsupported">
            <div class="unsupported-card">
              <i class="bi bi-exclamation-triangle"></i>
              <p>此工具不支援此檔案格式</p>
              <button v-if="unsupportedTarget" class="goto-btn" @click="goToTool">
                前往{{ getToolLabel(unsupportedTarget) }}
              </button>
              <button class="dismiss-btn" @click="dismissUnsupported">關閉</button>
            </div>
          </div>
        </Transition>

        <!-- 拖曳 hover 效果 -->
        <div v-if="isDragOver" class="drag-hover-overlay">
          <i class="bi bi-cloud-arrow-up-fill"></i>
          <p>放開以載入檔案</p>
        </div>

        <!-- 無檔案時顯示上傳區 -->
        <AppUploadZone
          v-if="!hasFile"
          :icon="uploadIcon"
          :label="uploadLabel"
          :accept="uploadAccept"
          @file="handleUploadFile"
        />

        <!-- Slider 比對模式 -->
        <div
          v-else-if="isComparing && resultPreviewUrl"
          ref="compareContainerRef"
          class="compare-slider-container"
        >
          <img :src="previewUrl!" alt="原圖" class="compare-img compare-img-original" />
          <img
            :src="resultPreviewUrl"
            alt="成果"
            class="compare-img compare-img-result"
            :style="{ clipPath: `inset(0 0 0 ${sliderPosition}%)` }"
          />
          <div
            class="slider-handle"
            :style="{ left: `${sliderPosition}%` }"
            @mousedown="startSliderDrag"
            @touchstart="startSliderDrag"
          >
            <div class="slider-line"></div>
            <div class="slider-grip">
              <i class="bi bi-grip-vertical"></i>
            </div>
          </div>
          <span class="compare-label compare-label-left">原圖</span>
          <span class="compare-label compare-label-right">成果</span>
        </div>

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
      </div>
    </main>

    <!-- 右側：設定面板 -->
    <aside class="settings-panel">
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
          @click="handleExecute"
        >
          <span v-if="executeLoading" class="spinner-border spinner-border-sm me-2"></span>
          <i v-else class="bi bi-play-fill me-2"></i>
          {{ executeLoading ? '處理中...' : executeLabel }}
        </button>
      </div>
    </aside>
  </div>
</template>

<style lang="scss" scoped>
.tool-layout {
  display: flex;
  height: calc(100vh - 40px);
  gap: 1rem;
  padding: 1rem;
}

// 左側子功能列表
.function-sidebar {
  position: relative;
  width: 180px;
  min-width: 180px;
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

  i {
    font-size: 1.1rem;
    width: 22px;
  }

  span {
    font-size: 0.9rem;
  }

  &:hover {
    color: var(--text-primary);
    background: var(--panel-bg-hover);
  }

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

  &.coming-soon {
    opacity: 0.5;
  }
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

.toolbar-btn {
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

  &:hover:not(:disabled) {
    opacity: 1;
  }

  &.disabled, &:disabled {
    opacity: 0.25;
    cursor: not-allowed;
  }

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

  &:hover:not(:disabled)::after {
    opacity: 1;
  }

  &.remove-btn:hover:not(:disabled) {
    background: rgba(220, 53, 69, 0.75);
    border-color: rgba(220, 53, 69, 0.5);
    color: #fff;
  }

  &.compare-btn:hover:not(:disabled),
  &.compare-btn.active {
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

// Slider 比對
.compare-slider-container {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  user-select: none;
}

.compare-img {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.compare-img-original {
  z-index: 1;
}

.compare-img-result {
  z-index: 2;
}

.slider-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 3;
  width: 4px;
  transform: translateX(-50%);
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
}

.slider-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
}

.slider-grip {
  position: relative;
  z-index: 4;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 50%;
  color: #333;
  font-size: 0.9rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.compare-label {
  position: absolute;
  bottom: 1rem;
  z-index: 5;
  padding: 0.25rem 0.75rem;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 4px;
  color: white;
  font-size: 0.75rem;
  pointer-events: none;

  &-left {
    left: 1rem;
  }

  &-right {
    right: 1rem;
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

  &:hover:not(.disabled) {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  &.active {
    background: var(--panel-bg-active);
    color: var(--text-primary);
  }

  &.disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
}

.preview-content {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  overflow: auto;
}

.preview-placeholder {
  text-align: center;
  color: var(--text-muted);

  i {
    font-size: 4rem;
    margin-bottom: 1rem;
  }

  p {
    font-size: 1rem;
  }
}

// 不支援 overlay
.unsupported-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.unsupported-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 2rem 2.5rem;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 16px;
  text-align: center;

  > i {
    font-size: 2.5rem;
    color: var(--color-warning);
  }

  > p {
    color: var(--text-primary);
    font-size: 1rem;
    margin: 0;
  }
}

.goto-btn {
  padding: 0.5rem 1.25rem;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
  }
}

.dismiss-btn {
  padding: 0.35rem 1rem;
  background: transparent;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    color: var(--text-primary);
    border-color: var(--text-muted);
  }
}

.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 0.2s ease;
}

.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}

// 拖曳 hover
.drag-hover-overlay {
  position: absolute;
  inset: 0;
  z-index: 50;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  background: rgba(96, 165, 250, 0.1);
  border: 2px dashed var(--color-accent);
  border-radius: 8px;
  pointer-events: none;

  i {
    font-size: 2.5rem;
    color: var(--color-accent);
  }

  p {
    color: var(--color-accent);
    font-size: 0.95rem;
    margin: 0;
  }
}

// 右側設定面板
.settings-panel {
  width: 320px;
  min-width: 320px;
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

.execute-btn {
  width: 100%;
  padding: 0.75rem 1rem;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.text-muted {
  color: var(--text-muted);
}
</style>
