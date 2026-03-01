<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ToolLayout from '@/components/ToolLayout.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import type { Task } from '@/types/task'

const router = useRouter()
const filesStore = useFilesStore()
const taskStore = useTaskStore()
const toast = useToast()
const { downloadFile } = useFileDownload()

// AI 環境與模型狀態
const aiEnvReady = ref(false)
const isModelDownloaded = ref(true)

async function checkAiEnvironment() {
  try {
    const res = await fetch('/api/setup/status')
    const status = await res.json()
    aiEnvReady.value = status.ai_env_ready
    
    if (!aiEnvReady.value && currentFunction.value === 'upscale') {
      toast.show('超解析功能需要安裝 AI 核心環境', { 
        type: 'info', 
        action: { label: '去安裝', callback: () => router.push('/setup') }
      })
    }
  } catch (e) {
    console.error('Failed to check AI status', e)
  }
}

async function checkModelStatus() {
  if (currentFunction.value !== 'upscale' || !upscaleModel.value) return
  try {
    // 假設後端有提供檢查模型端點
    const res = await fetch(`/api/models/check?category=upscale&model_id=${upscaleModel.value}`)
    const data = await res.json()
    isModelDownloaded.value = data.downloaded
  } catch (e) {
    // 若端點未實作，先預設為 true 以免卡住
    isModelDownloaded.value = true
  }
}

onMounted(() => {
  checkAiEnvironment()
})

// 子功能列表
const subFunctions = [
  { id: 'convert', name: '轉檔', icon: 'bi-arrow-repeat' },
  { id: 'remove-bg', name: '去背', icon: 'bi-eraser-fill' },
  { id: 'upscale', name: '超解析', icon: 'bi-arrows-angle-expand' },
  { id: 'filter', name: '濾鏡', icon: 'bi-palette-fill', comingSoon: true },
  { id: 'crop', name: '裁切', icon: 'bi-crop', comingSoon: true },
  { id: 'compress', name: '壓縮', icon: 'bi-file-zip-fill', comingSoon: true },
]

// 當前選擇的功能
const currentFunction = ref('convert')

// 檔案狀態
const hasFile = ref(false)
const fileId = ref<string | null>(null)
const sourceDir = ref<string | undefined>(undefined)
const currentFileName = ref('')
const isUploading = ref(false)
const error = ref<string | null>(null)

const isProcessing = ref(false)

// 比對結果
const resultPreviewUrl = ref<string | null>(null)
const currentTaskId = ref<string | null>(null)
const hasResult = computed(() => !!resultPreviewUrl.value)

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

// 去背設定
const removeBgMode = ref('auto')
const removeBgModes = [
  { value: 'auto', label: '自動偵測' },
  { value: 'person', label: '人物' },
  { value: 'product', label: '商品' },
  { value: 'animal', label: '動物' },
]

// 超解析設定
const upscaleScale = ref(4)
const upscaleScales = [
  { value: 2, label: '2x' },
  { value: 3, label: '3x' },
  { value: 4, label: '4x' },
]
const upscaleModel = ref('photo')
const upscaleModels = [
  { value: 'photo', label: '照片 / 寫實' },
  { value: 'anime', label: '動漫 / 插畫' },
]
const upscaleEngine = ref('waifu2x')
const upscaleSharpen = ref(false)

// currentFunction 與 upscaleModel 的 watcher（必須在 ref 宣告之後）
watch(currentFunction, (val) => {
  if (val === 'upscale') {
    checkAiEnvironment()
    checkModelStatus()
  }
})

watch(upscaleModel, () => {
  checkModelStatus()
})

// 轉檔設定
const convertFormat = ref('png')
const convertQuality = ref(90)
const convertFormats = [
  { value: 'png', label: 'PNG' },
  { value: 'jpg', label: 'JPEG' },
  { value: 'webp', label: 'WebP' },
  { value: 'gif', label: 'GIF' },
  { value: 'bmp', label: 'BMP' },
]

const executeDisabled = computed(() => !hasFile.value || !fileId.value || isProcessing.value)
const executeLoading = computed(() => isProcessing.value)

function handleExecute() {
  if (currentFunction.value === 'upscale') {
    if (!aiEnvReady.value) {
      router.push('/setup')
      return
    }
    if (!isModelDownloaded.value) {
      executeDownloadModel()
      return
    }
    executeUpscale()
  } else if (currentFunction.value === 'convert') {
    executeConvert()
  } else {
    executeMock()
  }
}

async function executeDownloadModel() {
  isProcessing.value = true
  toast.info(`正在啟動 ${upscaleModel.value} 下載任務...`)
  try {
    const res = await fetch(`/api/models/download?category=upscale&model_id=${upscaleModel.value}`, { method: 'POST' })
    const { task_id } = await res.json()
    toast.success('下載任務已提交')
    // 這裡未來可以監聽下載進度
  } catch (e) {
    toast.error('啟動下載失敗')
  } finally {
    isProcessing.value = false
  }
}

// 尺寸調整
type ResizeMode = 'original' | 'scale' | 'custom'
const convertResizeMode = ref<ResizeMode>('original')
const convertScale = ref(100)   // 10–200%
const convertWidth = ref<number | null>(null)
const convertHeight = ref<number | null>(null)

function selectFunction(id: string) {
  currentFunction.value = id
}

// 檔案上傳
async function handleFile(file: File, srcDir?: string) {
  hasFile.value = true
  sourceDir.value = srcDir
  currentFileName.value = file.name
  error.value = null
  imageInfo.value = null
  resultPreviewUrl.value = null
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
    error.value = e.message || '上傳失敗'
    toast.show(error.value!, { type: 'error', icon: 'bi-x-circle' })
  } finally {
    isUploading.value = false
  }
}

function handleDownload() {
  const task = currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null
  if (!task?.result) return
  const r = task.result as { output_file_id?: string }
  if (!r.output_file_id) return

  const baseName = currentFileName.value.replace(/\.[^.]+$/, '')
  const ext = currentFunction.value === 'convert'
    ? convertFormat.value
    : (currentFileName.value.split('.').pop() ?? 'png')

  let suffix = ''
  if (currentFunction.value === 'upscale') suffix = `_upscaled_${upscaleScale.value}x`
  else if (currentFunction.value === 'convert') suffix = '_converted'
  else if (currentFunction.value === 'remove-bg') suffix = '_nobg'

  const outputName = `${baseName}${suffix}.${ext}`
  downloadFile(r.output_file_id, outputName, sourceDir.value)
}

function handleRemoveFile() {
  hasFile.value = false
  fileId.value = null
  sourceDir.value = undefined
  currentFileName.value = ''
  error.value = null
  imageInfo.value = null
  resultPreviewUrl.value = null
  currentTaskId.value = null
  zoomLevel.value = 1
  panX.value = 0
  panY.value = 0
  fitPercent.value = 100
  isUploading.value = false
  isProcessing.value = false
  isLoadingInfo.value = false
}

// 載入圖片資訊
async function loadImageInfo() {
  if (!fileId.value) return
  isLoadingInfo.value = true
  try {
    const resp = await fetch(`/api/image/info/${fileId.value}`)
    if (!resp.ok) throw new Error('無法取得圖片資訊')
    imageInfo.value = await resp.json()
  } catch (e: any) {
    console.error('loadImageInfo error:', e)
  } finally {
    isLoadingInfo.value = false
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

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

// 通用任務提交
async function submitTask(
  apiPath: string,
  body: Record<string, unknown>,
  label: string,
  taskType: string,
) {
  if (!fileId.value) return
  isProcessing.value = true
  try {
    const resp = await fetch(apiPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || '提交任務失敗')
    }
    const { task_id: taskId } = await resp.json()
    currentTaskId.value = taskId
    resultPreviewUrl.value = null
    const task: Task = {
      taskId,
      taskType,
      status: 'pending',
      progress: 0,
      message: '任務已提交',
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label,
      fileName: currentFileName.value,
    }
    taskStore.addTask(task)
    toast.show(`${label}任務已提交`, { type: 'success', icon: 'bi-check-circle' })
  } catch (e: any) {
    toast.show(e.message || '提交失敗', { type: 'error', icon: 'bi-x-circle' })
  } finally {
    isProcessing.value = false
  }
}

function executeConvert() {
  submitTask('/api/image/convert', {
    file_id: fileId.value,
    output_format: convertFormat.value,
    quality: convertQuality.value,
    scale: convertResizeMode.value === 'scale' ? convertScale.value / 100 : undefined,
    width: convertResizeMode.value === 'custom' ? convertWidth.value ?? undefined : undefined,
    height: convertResizeMode.value === 'custom' ? convertHeight.value ?? undefined : undefined,
  }, '圖片轉檔', 'image.convert')
}

function executeUpscale() {
  submitTask('/api/image/upscale', {
    file_id: fileId.value,
    scale: upscaleScale.value,
    model: upscaleModel.value,
    engine: upscaleEngine.value,
    sharpen: upscaleSharpen.value,
  }, `超解析 ${upscaleScale.value}x`, 'image.upscale')
}

// Mock 用（未實作的功能）
function executeMock() {
  toast.show('此功能尚未實作', { type: 'info', icon: 'bi-info-circle' })
}

// 監聽任務完成 → 更新比對預覽 + 觸發下載 toast
watch(
  () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
  (task) => {
    if (!task) return
    if (task.status === 'completed' && task.result) {
      const r = task.result as { output_file_id?: string }
      if (r.output_file_id) {
        resultPreviewUrl.value = `/api/files/${r.output_file_id}/download`
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
    :result-preview-url="resultPreviewUrl"
    :execute-label="currentFunction === 'upscale' ? (!aiEnvReady ? '安裝 AI 核心' : (!isModelDownloaded ? '下載模型' : '執行處理')) : '執行處理'"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    hide-preview-tabs
    @select-function="selectFunction"
    @execute="handleExecute"
    @file="handleFile"
    @remove-file="handleRemoveFile"
    @download="handleDownload"
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
            :src="previewUrl"
            alt="原圖"
            :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoomLevel})` }"
            @load="onImageLoad"
          />
        </div>

        <!-- 圖片資訊欄 -->
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
        <!-- 去背設定 -->
        <div v-if="currentFunction === 'remove-bg'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-eraser-fill me-2"></i>去背設定
          </h6>

          <div class="form-group">
            <label>模式</label>
            <AppSelect v-model="removeBgMode" :options="removeBgModes" />
          </div>
        </div>

        <!-- 超解析設定 -->
        <div v-if="currentFunction === 'upscale'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-arrows-angle-expand me-2"></i>超解析
          </h6>

          <div class="form-group">
            <label>引擎</label>
            <div class="scale-options">
              <button
                class="scale-btn"
                :class="{ active: upscaleEngine === 'waifu2x' }"
                @click="upscaleEngine = 'waifu2x'"
              >waifu2x</button>
              <button
                class="scale-btn"
                :class="{ active: upscaleEngine === 'realesrgan' }"
                @click="upscaleEngine = 'realesrgan'"
              >Real-ESRGAN</button>
            </div>
            <small class="form-hint">
              waifu2x 細節保留較佳；Real-ESRGAN 紋理感更強
            </small>
          </div>

          <div class="form-group">
            <label>放大倍率</label>
            <div class="scale-options">
              <button
                v-for="s in upscaleScales"
                :key="s.value"
                class="scale-btn"
                :class="{ active: upscaleScale === s.value }"
                @click="upscaleScale = s.value"
              >
                {{ s.label }}
              </button>
            </div>
          </div>

          <div class="form-group">
            <label>內容類型</label>
            <AppSelect v-model="upscaleModel" :options="upscaleModels" />
          </div>

          <div class="form-group">
            <label class="toggle-label">
              <span>銳化後處理</span>
              <div
                class="toggle-switch"
                :class="{ active: upscaleSharpen }"
                @click="upscaleSharpen = !upscaleSharpen"
              >
                <div class="toggle-knob" />
              </div>
            </label>
            <small class="form-hint">補強邊緣銳利度，可改善油畫感</small>
          </div>
        </div>

        <!-- 轉檔設定 -->
        <div v-if="currentFunction === 'convert'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>轉檔</h6>

          <div class="form-group">
            <label>輸出格式</label>
            <AppSelect v-model="convertFormat" :options="convertFormats" />
          </div>

          <div v-if="convertFormat === 'jpg' || convertFormat === 'webp'" class="form-group">
            <label>品質: {{ convertQuality }}%</label>
            <AppRange v-model="convertQuality" :min="1" :max="100" />
            <small class="form-hint">數值越高品質越好、檔案越大</small>
          </div>

          <div class="form-group">
            <label>尺寸調整</label>
            <AppSelect
              v-model="convertResizeMode"
              :options="[
                { value: 'original', label: '原始尺寸' },
                { value: 'scale', label: '縮放比例' },
                { value: 'custom', label: '自訂尺寸' },
              ]"
            />
          </div>

          <div v-if="convertResizeMode === 'scale'" class="form-group">
            <label>縮放比例: {{ convertScale }}%</label>
            <AppRange v-model="convertScale" :min="10" :max="200" />
            <small class="form-hint">
              {{ imageInfo ? `${imageInfo.width} × ${imageInfo.height} → ${Math.round(imageInfo.width * convertScale / 100)} × ${Math.round(imageInfo.height * convertScale / 100)}` : '' }}
            </small>
          </div>

          <div v-if="convertResizeMode === 'custom'" class="form-group size-inputs">
            <div class="size-input-group">
              <label>寬度</label>
              <input
                type="number"
                class="form-input"
                placeholder="px"
                :value="convertWidth"
                min="1"
                @input="convertWidth = ($event.target as HTMLInputElement).value ? +($event.target as HTMLInputElement).value : null"
              />
            </div>
            <span class="size-separator">×</span>
            <div class="size-input-group">
              <label>高度</label>
              <input
                type="number"
                class="form-input"
                placeholder="px"
                :value="convertHeight"
                min="1"
                @input="convertHeight = ($event.target as HTMLInputElement).value ? +($event.target as HTMLInputElement).value : null"
              />
            </div>
          </div>
          <small v-if="convertResizeMode === 'custom'" class="form-hint">留空則等比縮放</small>
        </div>

        <!-- 濾鏡設定 -->
        <div v-if="currentFunction === 'filter'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-palette-fill me-2"></i>濾鏡設定
          </h6>
          <p class="text-muted">即將推出</p>
        </div>

        <!-- 裁切設定 -->
        <div v-if="currentFunction === 'crop'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-crop me-2"></i>裁切設定
          </h6>
          <p class="text-muted">即將推出</p>
        </div>

        <!-- 壓縮設定 -->
        <div v-if="currentFunction === 'compress'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-file-zip-fill me-2"></i>壓縮設定
          </h6>
          <p class="text-muted">即將推出</p>
        </div>
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
// 預覽顯示
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

  &.dragging {
    cursor: grabbing;
  }

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    transform-origin: center center;
    user-select: none;
    pointer-events: none;
  }
}


// 設定表單
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

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  label { font-size: 0.85rem; color: var(--text-secondary); }
}

.form-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: inherit;
  font-family: inherit;
  outline: none;
  transition: all 0.15s ease;

  &:focus {
    background: var(--input-bg-focus);
    border-color: var(--input-border-focus);
  }

  &::placeholder { color: var(--text-muted); }
}

.form-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.size-inputs {
  flex-direction: row;
  align-items: flex-end;
  gap: 0.5rem;
}

.size-input-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;

  label { font-size: 0.75rem; }
}

.size-separator {
  padding-bottom: 0.5rem;
  color: var(--text-muted);
}

// 超解析倍數按鈕
.scale-options {
  display: flex;
  gap: 0.5rem;
}

.scale-btn {
  flex: 1;
  padding: 0.5rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  &.active {
    background: rgba(96, 165, 250, 0.2);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }
}


.text-muted {
  color: var(--text-muted);
}

// Toggle switch
.toggle-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.toggle-switch {
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: var(--input-border);
  position: relative;
  transition: background 0.2s ease;
  flex-shrink: 0;

  &.active {
    background: var(--color-accent);
  }
}

.toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s ease;

  .toggle-switch.active & {
    transform: translateX(16px);
  }
}
</style>
