<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import SubtitlePanel from '@/components/video/SubtitlePanel.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppUploadZone from '@/components/common/AppUploadZone.vue'
import { useFilesStore } from '@/stores/files'

const filesStore = useFilesStore()

// 從 File 物件提取來源目錄（透過 preload 快取）
function extractSourceDir(file: File): string | undefined {
  return window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined
}

// 檢查是否有從首頁拖曳過來的檔案
onMounted(() => {
  const pending = filesStore.consumePendingFile()
  if (pending) {
    loadFile(pending.file, pending.sourceDir)
  }
})

// 子功能列表
const subFunctions = [
  { id: 'transcode', name: '轉檔', icon: 'bi-arrow-repeat' },
  { id: 'cut', name: '剪輯', icon: 'bi-scissors' },
  { id: 'compress', name: '壓縮', icon: 'bi-file-zip-fill' },
  { id: 'extract-audio', name: '提取音訊', icon: 'bi-music-note' },
  { id: 'subtitle', name: '字幕', icon: 'bi-badge-cc-fill' },
  { id: 'resize', name: '調整尺寸', icon: 'bi-aspect-ratio' },
]

const currentFunction = ref('transcode')

// 當前功能的標題與圖示
const currentFunctionInfo = computed(() => {
  const fn = subFunctions.find(f => f.id === currentFunction.value)
  return fn ? { name: fn.name, icon: fn.icon } : { name: '', icon: '' }
})

// 檔案狀態
const currentFile = ref<File | null>(null)
const originalPreview = ref<string | null>(null)
const resultPreview = ref<string | null>(null)
const isProcessing = ref(false)

// 上傳後的檔案 ID（用於需要後端處理的功能）
const fileId = ref<string | null>(null)
const isUploading = ref(false)
const sourceDir = ref<string | undefined>(undefined)

// 媒體資訊
interface MediaInfo {
  duration: number
  width: number
  height: number
  fps: number
  video_codec: string
  audio_codec: string
  bitrate: number
  file_size: number
}
const mediaInfo = ref<MediaInfo | null>(null)

const hasFile = computed(() => !!currentFile.value)
const hasResult = computed(() => !!resultPreview.value)

// 格式化工具
function formatDuration(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function formatBitrate(bps: number) {
  if (bps < 1000) return `${bps} bps`
  if (bps < 1000000) return `${(bps / 1000).toFixed(0)} Kbps`
  return `${(bps / 1000000).toFixed(1)} Mbps`
}

async function loadMediaInfo() {
  if (!fileId.value) return
  try {
    const response = await fetch(`/api/video/info/${fileId.value}`)
    if (response.ok) {
      mediaInfo.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load media info:', e)
  }
}

// 轉檔設定
const outputFormat = ref('mp4')
const videoCodec = ref('h264')
const audioCodec = ref('aac')
const resolution = ref('')
const crf = ref(23)

const formats = [
  { value: 'mp4', label: 'MP4' },
  { value: 'mkv', label: 'MKV' },
  { value: 'webm', label: 'WebM' },
  { value: 'avi', label: 'AVI' },
  { value: 'mov', label: 'MOV' },
]

const videoCodecs = [
  { value: 'h264', label: 'H.264' },
  { value: 'h265', label: 'H.265/HEVC' },
  { value: 'vp9', label: 'VP9' },
  { value: 'copy', label: '不重新編碼' },
]

const resolutions = [
  { value: '', label: '保持原始' },
  { value: '1920x1080', label: '1080p' },
  { value: '1280x720', label: '720p' },
  { value: '854x480', label: '480p' },
]

function selectFunction(id: string) {
  currentFunction.value = id
}

function handleExport() {
  console.log('Export video')
}

function executeProcess() {
  isProcessing.value = true
  setTimeout(() => {
    isProcessing.value = false
    resultPreview.value = originalPreview.value
  }, 2000)
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    loadFile(files[0])
  }
}

function loadFile(file: File, srcDir?: string) {
  currentFile.value = file
  sourceDir.value = srcDir
  originalPreview.value = URL.createObjectURL(file)
  resultPreview.value = null
  fileId.value = null
  mediaInfo.value = null
  // 自動上傳並取得媒體資訊
  ensureFileUploaded()
}

async function ensureFileUploaded() {
  if (fileId.value || !currentFile.value || isUploading.value) return

  isUploading.value = true
  try {
    const id = await filesStore.uploadFile(currentFile.value, sourceDir.value)
    fileId.value = id
    await loadMediaInfo()
  } catch (e) {
    console.error('File upload failed:', e)
  } finally {
    isUploading.value = false
  }
}

function handleSubtitleSubmit(taskId: string) {
  isProcessing.value = true
}

function handleSubtitleComplete(taskId: string) {
  isProcessing.value = false
}
</script>

<template>
  <ToolLayout
    title="影片工具"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-file="hasFile"
    :has-result="hasResult"
    @select-function="selectFunction"
    @export="handleExport"
  >
    <!-- 預覽區域 -->
    <template #preview="{ mode }">
      <AppUploadZone
        v-if="!hasFile"
        icon="bi-film"
        label="拖曳影片到這裡"
        accept="video/*"
        @file="loadFile"
      />

      <div v-else class="preview-display">
        <div class="video-wrapper">
          <video
            v-if="mode === 'original' || !hasResult"
            :src="originalPreview"
            controls
            class="video-player"
          ></video>
          <video
            v-else
            :src="resultPreview"
            controls
            class="video-player"
          ></video>
        </div>

        <!-- 媒體資訊 -->
        <div v-if="mediaInfo" class="media-info-bar">
          <div class="info-item">
            <i class="bi bi-aspect-ratio"></i>
            <span>{{ mediaInfo.width }}x{{ mediaInfo.height }}</span>
          </div>
          <div class="info-item">
            <i class="bi bi-clock"></i>
            <span>{{ formatDuration(mediaInfo.duration) }}</span>
          </div>
          <div class="info-item">
            <i class="bi bi-film"></i>
            <span>{{ mediaInfo.video_codec.toUpperCase() }}</span>
          </div>
          <div class="info-item">
            <i class="bi bi-volume-up"></i>
            <span>{{ mediaInfo.audio_codec.toUpperCase() }}</span>
          </div>
          <div class="info-item">
            <i class="bi bi-speedometer2"></i>
            <span>{{ formatBitrate(mediaInfo.bitrate) }}</span>
          </div>
          <div class="info-item">
            <i class="bi bi-camera-reels"></i>
            <span>{{ mediaInfo.fps.toFixed(1) }} fps</span>
          </div>
          <div class="info-item">
            <i class="bi bi-hdd"></i>
            <span>{{ formatFileSize(mediaInfo.file_size) }}</span>
          </div>
        </div>
        <div v-else-if="isUploading" class="media-info-bar loading">
          <div class="spinner-border spinner-border-sm" role="status"></div>
          <span>讀取媒體資訊...</span>
        </div>
      </div>
    </template>

    <!-- 設定面板 -->
    <template #settings>
      <div class="settings-form">
        <!-- 工具標題 -->
        <h6 class="settings-title">
          <i :class="['bi', currentFunctionInfo.icon, 'me-2']"></i>{{ currentFunctionInfo.name }}
        </h6>

        <!-- 轉檔設定 -->
        <div v-if="currentFunction === 'transcode'" class="function-settings">
          <div class="form-group">
            <label>輸出格式</label>
            <AppSelect v-model="outputFormat" :options="formats" />
          </div>

          <div class="form-group">
            <label>影片編碼</label>
            <AppSelect v-model="videoCodec" :options="videoCodecs" />
          </div>

          <div class="form-group">
            <label>解析度</label>
            <AppSelect v-model="resolution" :options="resolutions" />
          </div>

          <div class="form-group">
            <label>品質 (CRF): {{ crf }}</label>
            <AppRange v-model="crf" :min="0" :max="51" />
          </div>

          <button
            class="execute-btn"
            :disabled="!hasFile || isProcessing"
            @click="executeProcess"
          >
            <span v-if="isProcessing" class="spinner-border spinner-border-sm me-2"></span>
            {{ isProcessing ? '處理中...' : '執行轉檔' }}
          </button>
        </div>

        <!-- 其他功能（即將推出） -->
        <div v-if="currentFunction === 'cut'" class="function-settings">
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'compress'" class="function-settings">
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'extract-audio'" class="function-settings">
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'subtitle'" class="function-settings">
          <SubtitlePanel
            :fileId="fileId"
            :mediaInfo="mediaInfo"
            @submit="handleSubtitleSubmit"
            @complete="handleSubtitleComplete"
          />
        </div>

        <div v-if="currentFunction === 'resize'" class="function-settings">
          <p class="text-muted">即將推出</p>
        </div>
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.preview-display {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.video-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}

.video-player {
  max-width: 100%;
  max-height: 100%;
  border-radius: 8px;
}

.media-info-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 1rem;
  padding: 0.6rem 1rem;
  border-top: 1px solid var(--panel-border);

  &.loading {
    gap: 0.5rem;
    color: var(--text-muted);
    font-size: 0.85rem;
  }
}

.info-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-secondary);

  i {
    font-size: 0.7rem;
    color: var(--text-muted);
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

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  label { font-size: 0.85rem; color: var(--text-secondary); }
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
  margin-top: 0.5rem;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
  }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.text-muted { color: var(--text-muted); }
</style>
