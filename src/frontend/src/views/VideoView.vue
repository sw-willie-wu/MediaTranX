<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import SubtitlePanel from '@/components/video/SubtitlePanel.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import type { Task } from '@/types/task'

const filesStore = useFilesStore()
const taskStore = useTaskStore()
const toast = useToast()

// SubtitlePanel ref
const subtitlePanelRef = ref<InstanceType<typeof SubtitlePanel> | null>(null)

// Video element ref
const videoRef = ref<HTMLVideoElement | null>(null)

// 子功能列表
const subFunctions = [
  { id: 'transcode', name: '轉檔', icon: 'bi-arrow-repeat' },
  { id: 'cut', name: '剪輯', icon: 'bi-scissors' },
  { id: 'subtitle', name: '字幕', icon: 'bi-badge-cc-fill' },
]

const currentFunction = ref('transcode')

// View 專屬狀態
const resultPreview = ref<string | null>(null)
const isProcessing = ref(false)
const hasFile = ref(false)

// 上傳後的檔案 ID（用於需要後端處理的功能）
const fileId = ref<string | null>(null)
const isUploading = ref(false)
const sourceDir = ref<string | undefined>(undefined)
const currentFileName = ref<string>('')

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

// ========== 轉檔設定 ==========
const outputFormat = ref('mp4')
const videoCodec = ref('h264')
const resolution = ref('')
const crf = ref(23)

const audioFormatValues = ['mp3', 'aac', 'wav', 'flac']

const formats = [
  { value: 'mp4', label: 'MP4' },
  { value: 'mkv', label: 'MKV' },
  { value: 'webm', label: 'WebM' },
  { value: 'avi', label: 'AVI' },
  { value: 'mov', label: 'MOV' },
  { value: 'mp3', label: 'MP3（純音訊）' },
  { value: 'aac', label: 'AAC（純音訊）' },
  { value: 'wav', label: 'WAV（純音訊）' },
  { value: 'flac', label: 'FLAC（純音訊）' },
]

const isAudioFormat = computed(() => audioFormatValues.includes(outputFormat.value))

const videoCodecs = [
  { value: 'h264', label: 'H.264' },
  { value: 'h265', label: 'H.265/HEVC' },
  { value: 'vp9', label: 'VP9' },
  { value: 'copy', label: '不重新編碼' },
]

const resolutions = [
  { value: '', label: '保持原始' },
  { value: '3840x2160', label: '4K (3840x2160)' },
  { value: '2560x1440', label: '2K (2560x1440)' },
  { value: '1920x1080', label: '1080p (1920x1080)' },
  { value: '1280x720', label: '720p (1280x720)' },
  { value: '854x480', label: '480p (854x480)' },
  { value: 'custom', label: '自訂尺寸' },
]
const customResWidth = ref(1920)
const customResHeight = ref(1080)

const scaleAlgorithm = ref('bicubic')
const scaleAlgorithms = [
  { value: 'bicubic', label: 'Bicubic（預設）' },
  { value: 'lanczos', label: 'Lanczos（高品質）' },
  { value: 'spline', label: 'Spline（高品質）' },
  { value: 'bilinear', label: 'Bilinear（快速）' },
  { value: 'neighbor', label: 'Nearest Neighbor（像素風格）' },
]

// ========== 剪輯設定 ==========
const cutStartTime = ref('00:00:00')
const cutEndTime = ref('00:00:00')
const cutStreamCopy = ref(true)

function parseTimeToSeconds(time: string): number {
  const parts = time.split(':').map(Number)
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2]
  } else if (parts.length === 2) {
    return parts[0] * 60 + parts[1]
  }
  return Number(time) || 0
}

function secondsToTimeString(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

// ========== 剪輯時間軸 ==========
const trackRef = ref<HTMLDivElement | null>(null)
const dragging = ref<'start' | 'end' | null>(null)
const playheadPercent = ref(0)

const startPercent = computed(() => {
  if (!mediaInfo.value) return 0
  return (parseTimeToSeconds(cutStartTime.value) / mediaInfo.value.duration) * 100
})

const endPercent = computed(() => {
  if (!mediaInfo.value) return 100
  return (parseTimeToSeconds(cutEndTime.value) / mediaInfo.value.duration) * 100
})

const selectionStyle = computed(() => ({
  left: startPercent.value + '%',
  width: (endPercent.value - startPercent.value) + '%',
}))

function startDrag(handle: 'start' | 'end', e: MouseEvent | TouchEvent) {
  dragging.value = handle
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
  document.addEventListener('touchmove', onDragMove)
  document.addEventListener('touchend', onDragEnd)
}

function onDragMove(e: MouseEvent | TouchEvent) {
  if (!dragging.value || !trackRef.value || !mediaInfo.value) return
  const rect = trackRef.value.getBoundingClientRect()
  const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
  const percent = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
  const seconds = (percent / 100) * mediaInfo.value.duration

  if (dragging.value === 'start') {
    const endSec = parseTimeToSeconds(cutEndTime.value)
    cutStartTime.value = secondsToTimeString(Math.min(seconds, endSec - 1))
  } else {
    const startSec = parseTimeToSeconds(cutStartTime.value)
    cutEndTime.value = secondsToTimeString(Math.max(seconds, startSec + 1))
  }

  if (videoRef.value) {
    videoRef.value.currentTime = seconds
  }
}

function onDragEnd() {
  dragging.value = null
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  document.removeEventListener('touchmove', onDragMove)
  document.removeEventListener('touchend', onDragEnd)
}

function onTrackMouseDown(e: MouseEvent) {
  if (!trackRef.value || !mediaInfo.value) return
  const rect = trackRef.value.getBoundingClientRect()
  const percent = ((e.clientX - rect.left) / rect.width) * 100
  const seconds = (percent / 100) * mediaInfo.value.duration
  if (videoRef.value) videoRef.value.currentTime = seconds
}

function onTrackTouchStart(e: TouchEvent) {
  if (!trackRef.value || !mediaInfo.value) return
  const rect = trackRef.value.getBoundingClientRect()
  const percent = ((e.touches[0].clientX - rect.left) / rect.width) * 100
  const seconds = (percent / 100) * mediaInfo.value.duration
  if (videoRef.value) videoRef.value.currentTime = seconds
}

function onVideoTimeUpdate() {
  if (!videoRef.value || !mediaInfo.value) return
  playheadPercent.value = (videoRef.value.currentTime / mediaInfo.value.duration) * 100
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  document.removeEventListener('touchmove', onDragMove)
  document.removeEventListener('touchend', onDragEnd)
})

// ========== 音訊位元率設定（轉檔用） ==========
const audioBitrate = ref('192k')

const audioBitrates = [
  { value: '128k', label: '128 kbps' },
  { value: '192k', label: '192 kbps' },
  { value: '256k', label: '256 kbps' },
  { value: '320k', label: '320 kbps' },
]

const showBitrateOption = computed(() => isAudioFormat.value && !['wav', 'flac'].includes(outputFormat.value))

function selectFunction(id: string) {
  currentFunction.value = id
}

function handleExecute() {
  switch (currentFunction.value) {
    case 'transcode': executeTranscode(); break
    case 'cut': executeCut(); break
    case 'subtitle': subtitlePanelRef.value?.submitGenerate(); break
  }
}

const executeDisabled = computed(() => {
  if (currentFunction.value === 'subtitle') {
    return subtitlePanelRef.value?.isDisabled ?? true
  }
  return !hasFile.value || isProcessing.value || isUploading.value
})

const executeLoading = computed(() => {
  if (currentFunction.value === 'subtitle') {
    return subtitlePanelRef.value?.isLoading ?? false
  }
  return isProcessing.value
})

// ========== 通用任務提交 ==========
async function submitTask(apiPath: string, body: Record<string, unknown>, label: string) {
  if (!fileId.value) return

  isProcessing.value = true
  try {
    const response = await fetch(`/api/video/${apiPath}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || '提交任務失敗')
    }

    const data = await response.json()
    const taskId = data.task_id

    const task: Task = {
      taskId,
      taskType: `video.${apiPath.replace('-', '_')}`,
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
    resultPreview.value = 'submitted'
  } catch (e: any) {
    toast.show(e.message || '提交任務失敗', { type: 'error', icon: 'bi-x-circle' })
  } finally {
    isProcessing.value = false
  }
}

// ========== 各功能執行 ==========
async function executeTranscode() {
  if (isAudioFormat.value) {
    await submitTask('extract-audio', {
      file_id: fileId.value,
      audio_format: outputFormat.value,
      audio_bitrate: showBitrateOption.value ? audioBitrate.value : undefined,
    }, '提取音訊')
    return
  }

  let finalResolution = resolution.value
  if (resolution.value === 'custom') {
    finalResolution = `${customResWidth.value}x${customResHeight.value}`
  }

  await submitTask('transcode', {
    file_id: fileId.value,
    output_format: outputFormat.value,
    video_codec: videoCodec.value,
    audio_codec: 'aac',
    crf: crf.value,
    resolution: finalResolution || undefined,
    scale_algorithm: finalResolution ? scaleAlgorithm.value : undefined,
  }, '轉檔')
}

async function executeCut() {
  const startSeconds = parseTimeToSeconds(cutStartTime.value)
  const endSeconds = parseTimeToSeconds(cutEndTime.value)

  if (endSeconds <= startSeconds) {
    toast.show('結束時間必須大於開始時間', { type: 'error', icon: 'bi-x-circle' })
    return
  }

  await submitTask('cut', {
    file_id: fileId.value,
    start_time: startSeconds,
    end_time: endSeconds,
    stream_copy: cutStreamCopy.value,
  }, '剪輯')
}

async function handleFile(file: File, srcDir?: string) {
  hasFile.value = true
  sourceDir.value = srcDir
  resultPreview.value = null
  fileId.value = null
  mediaInfo.value = null
  currentFileName.value = file.name
  // 自動上傳並取得媒體資訊
  await ensureFileUploaded(file)
}

async function ensureFileUploaded(file: File) {
  if (fileId.value || isUploading.value) return

  isUploading.value = true
  try {
    const id = await filesStore.uploadFile(file, sourceDir.value)
    fileId.value = id
    await loadMediaInfo()
    // 設定剪輯預設結束時間
    if (mediaInfo.value) {
      cutEndTime.value = secondsToTimeString(mediaInfo.value.duration)
    }
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
    accept-type="video"
    upload-icon="bi-film"
    upload-label="拖曳影片到這裡"
    upload-accept="video/*"
    hide-preview-tabs
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    @select-function="selectFunction"
    @execute="handleExecute"
    @file="handleFile"
  >
    <!-- 預覽區域 -->
    <template #preview="{ file, previewUrl, mode }">
      <div class="preview-display">
        <div class="video-wrapper">
          <div class="video-container">
            <video
              ref="videoRef"
              :src="previewUrl"
              controls
              class="video-player"
              @timeupdate="onVideoTimeUpdate"
            ></video>
            <!-- 剪輯時間軸（覆蓋在影片底部） -->
            <div v-if="currentFunction === 'cut' && mediaInfo" class="cut-timeline">
              <div class="timeline-track" ref="trackRef"
                   @mousedown="onTrackMouseDown"
                   @touchstart.prevent="onTrackTouchStart">
                <div class="timeline-selection" :style="selectionStyle"></div>
                <div class="timeline-handle start" :style="{ left: startPercent + '%' }"
                     @mousedown.stop="startDrag('start', $event)"
                     @touchstart.stop.prevent="startDrag('start', $event)">
                </div>
                <div class="timeline-handle end" :style="{ left: endPercent + '%' }"
                     @mousedown.stop="startDrag('end', $event)"
                     @touchstart.stop.prevent="startDrag('end', $event)">
                </div>
                <div class="timeline-playhead" :style="{ left: playheadPercent + '%' }"></div>
                <div class="timeline-times">
                  <span :style="{ left: startPercent + '%' }">{{ cutStartTime }}</span>
                  <span :style="{ left: endPercent + '%' }">{{ cutEndTime }}</span>
                </div>
              </div>
            </div>
          </div>
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
        <!-- 轉檔設定 -->
        <div v-if="currentFunction === 'transcode'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>轉檔</h6>
          <div class="form-group">
            <label>輸出格式</label>
            <AppSelect v-model="outputFormat" :options="formats" />
          </div>

          <template v-if="!isAudioFormat">
            <div class="form-group">
              <label>影片編碼</label>
              <AppSelect v-model="videoCodec" :options="videoCodecs" />
            </div>

            <div class="form-group">
              <label>解析度</label>
              <AppSelect v-model="resolution" :options="resolutions" />
            </div>

            <div v-if="resolution === 'custom'" class="form-group size-inputs">
              <div class="size-input-group">
                <label>寬度</label>
                <input v-model.number="customResWidth" type="number" class="form-input" min="1" />
              </div>
              <span class="size-separator">x</span>
              <div class="size-input-group">
                <label>高度</label>
                <input v-model.number="customResHeight" type="number" class="form-input" min="1" />
              </div>
            </div>

            <div v-if="resolution" class="form-group">
              <label>縮放演算法</label>
              <AppSelect v-model="scaleAlgorithm" :options="scaleAlgorithms" />
            </div>

            <div class="form-group">
              <label>品質 (CRF): {{ crf }}</label>
              <AppRange v-model="crf" :min="0" :max="51" />
              <small class="form-hint">數值越小品質越高、檔案越大（建議 18-28）</small>
            </div>
          </template>

          <div v-if="showBitrateOption" class="form-group">
            <label>位元率</label>
            <AppSelect v-model="audioBitrate" :options="audioBitrates" />
          </div>

        </div>

        <!-- 剪輯設定 -->
        <div v-if="currentFunction === 'cut'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-scissors me-2"></i>剪輯</h6>
          <div class="form-group">
            <label>開始時間 (HH:MM:SS)</label>
            <input
              v-model="cutStartTime"
              type="text"
              class="form-input"
              placeholder="00:00:00"
            />
          </div>

          <div class="form-group">
            <label>結束時間 (HH:MM:SS)</label>
            <input
              v-model="cutEndTime"
              type="text"
              class="form-input"
              placeholder="00:00:00"
            />
          </div>

          <div class="form-group checkbox-group">
            <label class="checkbox-label">
              <input type="checkbox" v-model="cutStreamCopy" />
              <span>快速模式（不重新編碼）</span>
            </label>
            <small class="form-hint">關閉可獲得精確剪輯點，但速度較慢</small>
          </div>

        </div>

        <!-- 字幕設定 -->
        <div v-if="currentFunction === 'subtitle'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-badge-cc-fill me-2"></i>字幕</h6>
          <SubtitlePanel
            ref="subtitlePanelRef"
            :fileId="fileId"
            :mediaInfo="mediaInfo"
            @submit="handleSubtitleSubmit"
            @complete="handleSubtitleComplete"
          />
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
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}

.video-container {
  position: relative;
  display: flex;
  max-width: 100%;
  max-height: 100%;
  overflow: visible;
  margin-bottom: 1.5rem;
}

.video-player {
  display: block;
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

  &::placeholder {
    color: var(--text-muted);
  }
}

.form-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.checkbox-group {
  gap: 0.25rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--text-primary);

  input[type="checkbox"] {
    width: 16px;
    height: 16px;
    accent-color: var(--color-primary);
  }
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

  label {
    font-size: 0.75rem;
  }
}

.size-separator {
  padding-bottom: 0.5rem;
  color: var(--text-muted);
}

.text-muted { color: var(--text-muted); }

.cut-timeline {
  position: absolute;
  bottom: 12px;
  left: 0;
  right: 0;
  padding: 0 calc(0.75rem + 2px);
  z-index: 3;
}

.timeline-times {
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  margin-top: 4px;

  span {
    position: absolute;
    font-size: 0.85rem;
    color: var(--text-primary);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    transform: translateX(-50%);
  }
}

.timeline-track {
  position: relative;
  height: 20px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  cursor: pointer;
}

.timeline-selection {
  position: absolute;
  top: 0;
  height: 100%;
  background: rgba(124, 111, 173, 0.4);
  border-radius: 4px;
  pointer-events: none;
}

.timeline-handle {
  position: absolute;
  top: -2px;
  width: 6px;
  height: 24px;
  background: var(--color-primary);
  border-radius: 3px;
  cursor: ew-resize;
  transform: translateX(-50%);
  z-index: 2;
  transition: background 0.15s ease;

  &:hover, &:active {
    background: var(--color-accent);
    box-shadow: 0 0 8px rgba(124, 111, 173, 0.6);
  }
}

.timeline-playhead {
  position: absolute;
  top: 0;
  width: 2px;
  height: 100%;
  background: rgba(255, 255, 255, 0.7);
  pointer-events: none;
  z-index: 1;
  transform: translateX(-50%);
}
</style>
