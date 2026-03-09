<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import SubtitlePanel from '@/components/video/SubtitlePanel.vue'
import VideoTranscodePanel from '@/components/video/panels/VideoTranscodePanel.vue'
import VideoCutPanel from '@/components/video/panels/VideoCutPanel.vue'
import AppMediaInfoBar from '@/components/common/AppMediaInfoBar.vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import { apiFetch } from '@/composables/useApi'

const filesStore = useFilesStore()
const taskStore = useTaskStore()
const toast = useToast()
const { downloadFile } = useFileDownload()

// Panel refs
const transcodePanelRef = ref<InstanceType<typeof VideoTranscodePanel> | null>(null)
const cutPanelRef = ref<InstanceType<typeof VideoCutPanel> | null>(null)
const subtitlePanelRef = ref<InstanceType<typeof SubtitlePanel> | null>(null)

// Video element ref
const videoRef = ref<HTMLVideoElement | null>(null)

const subFunctions = [
  { id: 'transcode', name: '轉檔', icon: 'bi-arrow-repeat' },
  { id: 'cut', name: '剪輯', icon: 'bi-scissors' },
  { id: 'subtitle', name: '字幕', icon: 'bi-badge-cc-fill' },
]

const currentFunction = ref('transcode')

const hasFile = ref(false)
const fileId = ref<string | null>(null)
const isUploading = ref(false)
const sourceDir = ref<string | undefined>(undefined)
const currentFileName = ref<string>('')
const currentTaskId = ref<string | null>(null)
const resultPreview = ref<string | null>(null)
const isProcessing = ref(false)

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

const mediaInfoItems = computed(() => {
  if (!mediaInfo.value) return []
  const m = mediaInfo.value
  return [
    { icon: 'bi-aspect-ratio', label: `${m.width}x${m.height}` },
    { icon: 'bi-clock', label: formatDuration(m.duration) },
    { icon: 'bi-film', label: m.video_codec.toUpperCase() },
    { icon: 'bi-volume-up', label: m.audio_codec.toUpperCase() },
    { icon: 'bi-speedometer2', label: formatBitrate(m.bitrate) },
    { icon: 'bi-camera-reels', label: `${m.fps.toFixed(1)} fps` },
    { icon: 'bi-hdd', label: formatFileSize(m.file_size) },
  ]
})

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
    const response = await apiFetch(`/video/info/${fileId.value}`)
    if (response.ok) mediaInfo.value = await response.json()
  } catch (e) {
    console.error('Failed to load media info:', e)
  }
}

// ========== 剪輯狀態（共享給時間軸與 VideoCutPanel） ==========
const cutStartTime = ref('00:00:00')
const cutEndTime = ref('00:00:00')
const cutStreamCopy = ref(true)

function parseTimeToSeconds(time: string): number {
  const parts = time.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
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

  if (videoRef.value) videoRef.value.currentTime = seconds
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

// ========== 路由執行 ==========
function selectFunction(id: string) {
  currentFunction.value = id
}

function handleExecute() {
  switch (currentFunction.value) {
    case 'transcode': transcodePanelRef.value?.execute(); break
    case 'cut': cutPanelRef.value?.execute(); break
    case 'subtitle': subtitlePanelRef.value?.submitGenerate(); break
  }
}

const executeDisabled = computed(() => {
  if (currentFunction.value === 'subtitle') return subtitlePanelRef.value?.isDisabled ?? true
  if (currentFunction.value === 'transcode') return transcodePanelRef.value?.isDisabled ?? (!hasFile.value || isProcessing.value)
  if (currentFunction.value === 'cut') return cutPanelRef.value?.isDisabled ?? (!hasFile.value || isProcessing.value)
  return !hasFile.value || isProcessing.value || isUploading.value
})

const executeLoading = computed(() => {
  if (currentFunction.value === 'subtitle') return subtitlePanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'transcode') return transcodePanelRef.value?.isLoading ?? isProcessing.value
  if (currentFunction.value === 'cut') return cutPanelRef.value?.isLoading ?? isProcessing.value
  return isProcessing.value
})

function handlePanelSubmit(taskId: string) {
  currentTaskId.value = taskId
  resultPreview.value = 'submitted'
}

function handleSubtitleSubmit(_taskId: string) {
  isProcessing.value = true
}

function handleSubtitleComplete(_taskId: string) {
  isProcessing.value = false
}

// ========== 檔案處理 ==========
async function handleFile(file: File, srcDir?: string) {
  hasFile.value = true
  sourceDir.value = srcDir
  resultPreview.value = null
  fileId.value = null
  mediaInfo.value = null
  currentFileName.value = file.name
  await ensureFileUploaded(file)
}

async function ensureFileUploaded(file: File) {
  if (fileId.value || isUploading.value) return
  isUploading.value = true
  try {
    const id = await filesStore.uploadFile(file, sourceDir.value)
    fileId.value = id
    await loadMediaInfo()
    if (mediaInfo.value) {
      cutEndTime.value = secondsToTimeString(mediaInfo.value.duration)
    }
  } catch (e) {
    console.error('File upload failed:', e)
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
  const isAudio = transcodePanelRef.value?.isAudioFormat ?? false
  const fmt = transcodePanelRef.value?.outputFormat ?? 'mp4'
  const suffix = currentFunction.value === 'cut' ? '_cut' : '_transcoded'
  const outputName = `${baseName}${suffix}.${fmt}`
  downloadFile(r.output_file_id, outputName, sourceDir.value)
}

// 監聽任務完成 → 帶下載的 toast
watch(
  () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
  (task) => {
    if (!task || task.status !== 'completed' || !task.result) return
    const r = task.result as { output_file_id?: string }
    if (!r.output_file_id) return
    toast.show(`${task.label ?? '處理'} 完成`, {
      type: 'success',
      icon: 'bi-check-circle',
      action: { label: '下載', callback: () => handleDownload() },
    })
  },
  { deep: true }
)
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
    @download="handleDownload"
  >
    <!-- 預覽區域 -->
    <template #preview="{ previewUrl }">
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
              <div
                class="timeline-track"
                ref="trackRef"
                @mousedown="onTrackMouseDown"
                @touchstart.prevent="onTrackTouchStart"
              >
                <div class="timeline-selection" :style="selectionStyle"></div>
                <div
                  class="timeline-handle start"
                  :style="{ left: startPercent + '%' }"
                  @mousedown.stop="startDrag('start', $event)"
                  @touchstart.stop.prevent="startDrag('start', $event)"
                ></div>
                <div
                  class="timeline-handle end"
                  :style="{ left: endPercent + '%' }"
                  @mousedown.stop="startDrag('end', $event)"
                  @touchstart.stop.prevent="startDrag('end', $event)"
                ></div>
                <div class="timeline-playhead" :style="{ left: playheadPercent + '%' }"></div>
                <div class="timeline-times">
                  <span :style="{ left: startPercent + '%' }">{{ cutStartTime }}</span>
                  <span :style="{ left: endPercent + '%' }">{{ cutEndTime }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <AppMediaInfoBar
          v-if="mediaInfo || isUploading"
          :items="mediaInfoItems"
          :loading="isUploading && !mediaInfo"
          loading-text="讀取媒體資訊..."
        />
      </div>
    </template>

    <!-- 設定面板 -->
    <template #settings>
      <div class="settings-form">
        <VideoTranscodePanel
          v-if="currentFunction === 'transcode'"
          ref="transcodePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <VideoCutPanel
          v-else-if="currentFunction === 'cut'"
          ref="cutPanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          v-model:start-time="cutStartTime"
          v-model:end-time="cutEndTime"
          v-model:stream-copy="cutStreamCopy"
          @submit="handlePanelSubmit"
        />

        <div v-else-if="currentFunction === 'subtitle'" class="function-settings">
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
