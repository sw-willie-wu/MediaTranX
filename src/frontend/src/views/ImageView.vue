<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ToolLayout from '@/components/ToolLayout.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import ImageConvertPanel from '@/components/image/panels/ImageConvertPanel.vue'
import ImageUpscalePanel from '@/components/image/panels/ImageUpscalePanel.vue'
import ImageRemoveBgPanel from '@/components/image/panels/ImageRemoveBgPanel.vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import { apiFetch, getApiBase } from '@/composables/useApi'

const router = useRouter()
const filesStore = useFilesStore()
const taskStore = useTaskStore()
const toast = useToast()
const { downloadFile } = useFileDownload()

// Panel refs
const convertPanelRef = ref<InstanceType<typeof ImageConvertPanel> | null>(null)
const upscalePanelRef = ref<InstanceType<typeof ImageUpscalePanel> | null>(null)
const removeBgPanelRef = ref<InstanceType<typeof ImageRemoveBgPanel> | null>(null)

// AI 環境狀態
const aiEnvReady = ref(false)

async function checkAiEnvironment() {
  try {
    const res = await apiFetch('/setup/status')
    const status = await res.json()
    aiEnvReady.value = status.ai_env_ready

    if (!aiEnvReady.value && currentFunction.value === 'upscale') {
      toast.show('超解析功能需要安裝 AI 核心環境', {
        type: 'info',
        action: { label: '去安裝', callback: () => router.push('/setup') },
      })
    }
  } catch (e) {
    console.error('Failed to check AI status', e)
  }
}

onMounted(() => {
  checkAiEnvironment()
})

const subFunctions = [
  { id: 'convert', name: '轉檔', icon: 'bi-arrow-repeat' },
  { id: 'remove-bg', name: '去背', icon: 'bi-eraser-fill' },
  { id: 'upscale', name: '超解析', icon: 'bi-arrows-angle-expand' },
  { id: 'filter', name: '濾鏡', icon: 'bi-palette-fill', comingSoon: true },
  { id: 'crop', name: '裁切', icon: 'bi-crop', comingSoon: true },
  { id: 'compress', name: '壓縮', icon: 'bi-file-zip-fill', comingSoon: true },
]

const currentFunction = ref('convert')

watch(currentFunction, (val) => {
  if (val === 'upscale') {
    checkAiEnvironment()
  }
})

// 檔案狀態
const hasFile = ref(false)
const fileId = ref<string | null>(null)
const sourceDir = ref<string | undefined>(undefined)
const currentFileName = ref('')
const isUploading = ref(false)
const currentTaskId = ref<string | null>(null)

// 歷史紀錄（處理結果堆疊）
interface HistoryEntry {
  fileId: string
  previewUrl: string
  outputFilename: string
}
const historyStack = ref<HistoryEntry[]>([])
const canGoBack = computed(() => historyStack.value.length > 0)
const activeFileId = computed(() => historyStack.value.at(-1)?.fileId ?? fileId.value)
const activePreviewUrl = computed(() => historyStack.value.at(-1)?.previewUrl ?? null)
const hasResult = computed(() => canGoBack.value)

function handleGoBack() {
  historyStack.value.pop()
  loadImageInfo()
}

// 縮放 & 拖曳
const zoomLevel = ref(1)
const panX = ref(0)
const panY = ref(0)
const isDragging = ref(false)
const imgRef = ref<HTMLImageElement | null>(null)
const imageContainerRef = ref<HTMLElement | null>(null)
const fitPercent = ref(100)

function onImageLoad() {
  if (!imgRef.value) return
  const naturalW = imgRef.value.naturalWidth
  if (!naturalW) return
  fitPercent.value = Math.round((imgRef.value.clientWidth / naturalW) * 100)
}

const zoomPercent = computed(() => Math.round(fitPercent.value * zoomLevel.value))

function clampPan(px: number, py: number) {
  if (!imgRef.value || !imageContainerRef.value) return { x: px, y: py }
  const cW = imageContainerRef.value.clientWidth
  const cH = imageContainerRef.value.clientHeight
  const scaledW = imgRef.value.clientWidth * zoomLevel.value
  const scaledH = imgRef.value.clientHeight * zoomLevel.value
  const maxX = Math.max(0, (scaledW - cW) / 2)
  const maxY = Math.max(0, (scaledH - cH) / 2)
  return {
    x: Math.max(-maxX, Math.min(maxX, px)),
    y: Math.max(-maxY, Math.min(maxY, py)),
  }
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const step = e.deltaY > 0 ? -0.1 : 0.1
  zoomLevel.value = Math.max(0.1, Math.min(10, +(zoomLevel.value + step).toFixed(1)))
  const c = clampPan(panX.value, panY.value)
  panX.value = c.x
  panY.value = c.y
}

let _dragStartX = 0
let _dragStartY = 0
let _panStartX = 0
let _panStartY = 0

function onMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  e.preventDefault()
  isDragging.value = true
  _dragStartX = e.clientX
  _dragStartY = e.clientY
  _panStartX = panX.value
  _panStartY = panY.value
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e: MouseEvent) {
  if (!isDragging.value) return
  const c = clampPan(_panStartX + e.clientX - _dragStartX, _panStartY + e.clientY - _dragStartY)
  panX.value = c.x
  panY.value = c.y
}

function onMouseUp() {
  isDragging.value = false
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
})

// 圖片資訊
interface ImageInfo {
  width: number
  height: number
  format: string
  mode: string
  file_size: number
}
const imageInfo = ref<ImageInfo | null>(null)
const isLoadingInfo = ref(false)

const imageInfoItems = computed<InfoItem[]>(() => {
  if (!imageInfo.value) return []
  const info = imageInfo.value
  return [
    { icon: 'bi-aspect-ratio', label: `${info.width} × ${info.height}` },
    { icon: 'bi-file-earmark', label: info.format ?? '—' },
    { icon: 'bi-palette', label: info.mode },
    { icon: 'bi-hdd', label: formatSize(info.file_size) },
    { icon: 'bi-zoom-in', label: `${zoomPercent.value}%` },
  ]
})

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function loadImageInfo() {
  if (!activeFileId.value) return
  isLoadingInfo.value = true
  try {
    const resp = await apiFetch(`/image/info/${activeFileId.value}`)
    if (!resp.ok) throw new Error('無法取得圖片資訊')
    imageInfo.value = await resp.json()
  } catch (e: any) {
    console.error('loadImageInfo error:', e)
  } finally {
    isLoadingInfo.value = false
  }
}

// execute label
const executeLabel = computed(() => {
  if (currentFunction.value === 'upscale' && !aiEnvReady.value) return '安裝 AI 核心'
  return '執行處理'
})

const executeDisabled = computed(() => !hasFile.value || !fileId.value || isUploading.value)
const executeLoading = computed(() => {
  if (currentFunction.value === 'convert') return convertPanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'upscale') return upscalePanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'remove-bg') return removeBgPanelRef.value?.isLoading ?? false
  return false
})

function selectFunction(id: string) {
  currentFunction.value = id
}

function handleExecute() {
  if (currentFunction.value === 'upscale') {
    if (!aiEnvReady.value) { router.push('/setup'); return }
    upscalePanelRef.value?.execute()
  } else if (currentFunction.value === 'convert') {
    convertPanelRef.value?.execute()
  } else if (currentFunction.value === 'remove-bg') {
    removeBgPanelRef.value?.execute()
  } else {
    toast.show('此功能尚未實作', { type: 'info', icon: 'bi-info-circle' })
  }
}

function handlePanelSubmit(taskId: string) {
  currentTaskId.value = taskId
}

async function handleFile(file: File, srcDir?: string) {
  hasFile.value = true
  sourceDir.value = srcDir
  currentFileName.value = file.name
  imageInfo.value = null
  historyStack.value = []
  currentTaskId.value = null
  zoomLevel.value = 1
  panX.value = 0
  panY.value = 0
  fitPercent.value = 100

  isUploading.value = true
  try {
    fileId.value = await filesStore.uploadFile(file, srcDir)
    await loadImageInfo()
  } catch (e: any) {
    toast.show(e.message || '上傳失敗', { type: 'error', icon: 'bi-x-circle' })
  } finally {
    isUploading.value = false
  }
}

function handleDownload() {
  const latest = historyStack.value.at(-1)
  if (!latest) return
  downloadFile(latest.fileId, latest.outputFilename, sourceDir.value)
}

function handleRemoveFile() {
  hasFile.value = false
  fileId.value = null
  sourceDir.value = undefined
  currentFileName.value = ''
  imageInfo.value = null
  historyStack.value = []
  currentTaskId.value = null
  zoomLevel.value = 1
  panX.value = 0
  panY.value = 0
  fitPercent.value = 100
  isUploading.value = false
  isLoadingInfo.value = false
}

// 監聽任務完成 → 推入歷史堆疊 + toast
watch(
  () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
  (task) => {
    if (!task) return
    if (task.status === 'completed' && task.result) {
      const r = task.result as { output_file_id?: string; output_filename?: string }
      if (r.output_file_id) {
        const url = `${getApiBase()}/files/${r.output_file_id}/download`
        historyStack.value.push({
          fileId: r.output_file_id,
          previewUrl: url,
          outputFilename: r.output_filename ?? `${currentFileName.value.replace(/\.[^.]+$/, '')}_result`,
        })
        loadImageInfo()
        toast.show(`${task.label ?? '處理'} 完成`, {
          type: 'success',
          icon: 'bi-check-circle',
          action: { label: '下載', callback: () => handleDownload() },
        })
      }
    }
  },
  { deep: true }
)
</script>

<template>
  <ToolLayout
    title="圖片工具"
    accept-type="image"
    upload-icon="bi-cloud-arrow-up-fill"
    upload-label="拖曳圖片到這裡"
    upload-accept="image/*"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :result-preview-url="activePreviewUrl"
    :can-go-back="canGoBack"
    :execute-label="executeLabel"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    hide-preview-tabs
    @select-function="selectFunction"
    @execute="handleExecute"
    @file="handleFile"
    @remove-file="handleRemoveFile"
    @download="handleDownload"
    @go-back="handleGoBack"
  >
    <!-- 預覽區域 -->
    <template #preview="{ previewUrl }">
      <div class="preview-display">
        <div
          ref="imageContainerRef"
          class="preview-image"
          :class="{ dragging: isDragging }"
          @wheel.prevent="onWheel"
          @mousedown="onMouseDown"
        >
          <img
            ref="imgRef"
            :src="activePreviewUrl ?? previewUrl"
            alt="原圖"
            :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoomLevel})` }"
            @load="onImageLoad"
          />
        </div>

        <AppMediaInfoBar
          v-if="imageInfo || isLoadingInfo || isUploading"
          :items="imageInfoItems"
          :loading="(isLoadingInfo || isUploading) && !imageInfo"
          loading-text="讀取圖片資訊..."
        />
      </div>
    </template>

    <!-- 設定面板 -->
    <template #settings>
      <div class="settings-form">
        <ImageConvertPanel
          v-if="currentFunction === 'convert'"
          ref="convertPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :image-info="imageInfo"
          @submit="handlePanelSubmit"
        />

        <ImageUpscalePanel
          v-else-if="currentFunction === 'upscale'"
          ref="upscalePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :ai-env-ready="aiEnvReady"
          @submit="handlePanelSubmit"
        />

        <ImageRemoveBgPanel
          v-else-if="currentFunction === 'remove-bg'"
          ref="removeBgPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <div v-else class="function-settings">
          <h6 class="settings-title">
            <i
              class="bi me-2"
              :class="{
                'bi-palette-fill': currentFunction === 'filter',
                'bi-crop': currentFunction === 'crop',
                'bi-file-zip-fill': currentFunction === 'compress',
              }"
            ></i>
            {{ { filter: '濾鏡設定', crop: '裁切設定', compress: '壓縮設定' }[currentFunction] }}
          </h6>
          <p class="text-muted">即將推出</p>
        </div>
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.preview-display {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.preview-image {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  overflow: hidden;
  cursor: grab;

  &.dragging { cursor: grabbing; }

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    transform-origin: center center;
    user-select: none;
    pointer-events: none;
  }
}

.settings-form { color: var(--text-primary); }

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
}

.text-muted { color: var(--text-muted); }
</style>
