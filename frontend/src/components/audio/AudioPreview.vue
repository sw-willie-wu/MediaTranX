<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'

const props = defineProps<{
  previewUrl: string | null
  file: File | null
}>()

// 瀏覽器不支援預覽的格式
const UNSUPPORTED_EXTS = new Set(['.amr', '.wma', '.opus', '.ape', '.ac3', '.dts'])
const previewUnsupported = computed(() => {
  if (!props.file) return false
  const ext = props.file.name.replace(/.*\./, '.').toLowerCase()
  return UNSUPPORTED_EXTS.has(ext)
})

// ── Refs ──────────────────────────────────────────────────────────────────
const audioRef       = ref<HTMLAudioElement | null>(null)
const waveformCanvas = ref<HTMLCanvasElement | null>(null)

// ── Per-file playback position cache ─────────────────────────────────────
const _timeCache = new Map<string, number>()
let _lastUrl = ''

// ── Waveform state ────────────────────────────────────────────────────────
let waveformData: Float32Array | null = null
let playheadRatio = 0
const decodeFailed = ref(false)

// ── Zoom & Pan state ─────────────────────────────────────────────────────
let zoomLevel = 1        // 1 = 全部顯示，越大越放大
let viewOffset = 0       // 0~1，目前檢視的起始位置（佔全長比例）
let isDragging = false
let hasDragged = false  // 是否有實際移動過（區分 click vs drag）
let dragStartX = 0
let dragStartOffset = 0
let totalDuration = 0  // 秒

// 波形快取：避免切換檔案時重複解碼
const _waveformCache = new Map<string, { mono: Float32Array; duration: number }>()

async function loadWaveform(url: string) {
  const canvas = waveformCanvas.value
  if (!canvas) return
  waveformData = null

  // 命中快取 → 直接用
  const cached = _waveformCache.get(url)
  if (cached) {
    waveformData = cached.mono
    totalDuration = cached.duration
    durationStr.value = formatTime(totalDuration)
    playheadRatio = 0
    drawWaveform()
    return
  }

  try {
    const response = await fetch(url)
    const arrayBuffer = await response.arrayBuffer()
    const ctx = new AudioContext()
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer)
    await ctx.close()

    // Mix down to mono
    const nCh = audioBuffer.numberOfChannels
    const len  = audioBuffer.length
    const mono = new Float32Array(len)
    for (let c = 0; c < nCh; c++) {
      const ch = audioBuffer.getChannelData(c)
      for (let i = 0; i < len; i++) mono[i] += ch[i] / nCh
    }
    waveformData = mono
    if (audioBuffer.duration > 0) {
      totalDuration = audioBuffer.duration
      durationStr.value = formatTime(totalDuration)
    }

    // 存入快取
    _waveformCache.set(url, { mono, duration: totalDuration })

    playheadRatio = 0
    drawWaveform()
  } catch (e) {
    console.warn('Waveform decode failed:', e)
    decodeFailed.value = true
  }
}

function drawWaveform() {
  const canvas = waveformCanvas.value
  if (!canvas || !waveformData) return

  const ctx  = canvas.getContext('2d')!
  const W    = canvas.width
  const H    = canvas.height
  const data = waveformData

  // 可視範圍（在全長中的比例）
  const viewWidth = 1 / zoomLevel
  const startRatio = viewOffset
  const endRatio = Math.min(startRatio + viewWidth, 1)

  // 對應的 sample 範圍
  const startSample = Math.floor(startRatio * data.length)
  const endSample = Math.ceil(endRatio * data.length)
  const visibleSamples = endSample - startSample
  const step = Math.max(1, Math.ceil(visibleSamples / W))

  // playhead 在畫面上的 x 位置
  const phRatioInView = (playheadRatio - startRatio) / viewWidth
  const ph = Math.round(phRatioInView * W)

  ctx.clearRect(0, 0, W, H)

  // 波形區域（扣掉底部時間軸）
  const waveH = H - 24
  const midY = waveH / 2

  // centre baseline
  ctx.fillStyle = 'rgba(255,255,255,0.05)'
  ctx.fillRect(0, midY, W, 1)

  for (let x = 0; x < W; x++) {
    const sampleStart = startSample + Math.floor(x * visibleSamples / W)
    let min = 0, max = 0
    for (let j = 0; j < step; j++) {
      const v = data[sampleStart + j] ?? 0
      if (v < min) min = v
      if (v > max) max = v
    }
    const amp  = (max - min) / 2
    const barH = Math.max(1, amp * waveH * 0.88)
    const y    = midY - barH / 2

    ctx.fillStyle = x < ph
      ? 'rgba(170, 140, 240, 0.95)'
      : 'rgba(140, 120, 200, 0.7)'
    ctx.fillRect(x, y, 1, barH)
  }

  // playhead line
  if (ph >= 0 && ph <= W) {
    ctx.fillStyle = 'rgba(230, 210, 255, 0.9)'
    ctx.fillRect(ph, 0, 1, H)
  }

  // ── 時間軸 ──
  if (totalDuration <= 0) return

  const timelineH = 24
  const timelineY = H - timelineH

  // 背景
  ctx.fillStyle = 'rgba(0, 0, 0, 0.3)'
  ctx.fillRect(0, timelineY, W, timelineH)

  // 可視範圍的時間
  const startTime = startRatio * totalDuration
  const endTime = endRatio * totalDuration
  const visibleDuration = endTime - startTime

  // 自動選擇刻度間隔
  const intervals = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
  const minPixelGap = 60
  const targetInterval = visibleDuration / (W / minPixelGap)
  let tickInterval = intervals.find(i => i >= targetInterval) ?? 600

  // 畫刻度
  ctx.fillStyle = 'rgba(255, 255, 255, 0.5)'
  ctx.font = '18px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'

  const firstTick = Math.ceil(startTime / tickInterval) * tickInterval
  for (let t = firstTick; t <= endTime; t += tickInterval) {
    const x = ((t - startTime) / visibleDuration) * W

    // 刻度線
    ctx.fillStyle = 'rgba(255, 255, 255, 0.3)'
    ctx.fillRect(Math.round(x), timelineY, 1, 6)

    // 時間文字（interval < 1s 時顯示毫秒）
    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)'
    const label = formatTime(t, tickInterval < 1)
    ctx.fillText(label, x, timelineY + 7)
  }
}

// ── Audio events ──────────────────────────────────────────────────────────
function onTimeUpdate() {
  const el = audioRef.value
  if (!el || !el.duration) return
  playheadRatio = el.currentTime / el.duration
  currentTimeStr.value = formatTime(el.currentTime)
  durationStr.value = formatTime(el.duration)
  drawWaveform()
}

function onLoadedMetadata() {
  const el = audioRef.value
  if (el) {
    durationStr.value = formatTime(el.duration)
    totalDuration = el.duration
    // 還原快取的播放位置
    const url = props.previewUrl
    if (url && _timeCache.has(url)) {
      el.currentTime = Math.min(_timeCache.get(url)!, el.duration)
      playheadRatio = el.currentTime / el.duration
      currentTimeStr.value = formatTime(el.currentTime)
    }
    drawWaveform()
  }
}

function onEnded() {
  playheadRatio = 1
  isPlaying.value = false
  drawWaveform()
}

// ── Play/Pause ───────────────────────────────────────────────────────────
const isPlaying = ref(false)
const currentTimeStr = ref('0:00')
const durationStr = ref('0:00')

function togglePlay() {
  const el = audioRef.value
  if (!el) return
  if (el.paused) { el.play(); isPlaying.value = true }
  else { el.pause(); isPlaying.value = false }
}

function formatTime(s: number, showMs = false): string {
  if (!isFinite(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  const base = `${m}:${sec.toString().padStart(2, '0')}`
  if (!showMs) return base
  const ms = Math.round((s % 1) * 10)
  return `${base}.${ms}`
}

// ── Seek on waveform click ────────────────────────────────────────────────
function onWaveformClick(e: MouseEvent) {
  if (hasDragged) { hasDragged = false; return }
  const canvas = waveformCanvas.value
  const el = audioRef.value
  if (!canvas || !el || !el.duration) return
  const rect = canvas.getBoundingClientRect()
  const clickRatio = (e.clientX - rect.left) / rect.width
  // 轉換回全長比例
  const viewWidth = 1 / zoomLevel
  const ratio = viewOffset + clickRatio * viewWidth
  el.currentTime = Math.max(0, Math.min(1, ratio)) * el.duration
  playheadRatio = ratio
  drawWaveform()
}

// ── Zoom (scroll wheel) ──────────────────────────────────────────────────
function onWheelZoom(e: WheelEvent) {
  e.preventDefault()
  const canvas = waveformCanvas.value
  if (!canvas || !waveformData) return

  const rect = canvas.getBoundingClientRect()
  const cursorRatio = (e.clientX - rect.left) / rect.width  // 游標在畫面上的比例
  const viewWidth = 1 / zoomLevel
  const cursorInTrack = viewOffset + cursorRatio * viewWidth  // 游標對應的全長位置

  // 調整 zoom
  const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2
  zoomLevel = Math.max(1, Math.min(200, zoomLevel * factor))

  // 重新計算 offset，讓游標位置不動
  const newViewWidth = 1 / zoomLevel
  viewOffset = Math.max(0, Math.min(1 - newViewWidth, cursorInTrack - cursorRatio * newViewWidth))

  drawWaveform()
}

// ── Pan (drag) ───────────────────────────────────────────────────────────
function onDragStart(e: MouseEvent) {
  if (zoomLevel <= 1) return
  isDragging = true
  hasDragged = false
  dragStartX = e.clientX
  dragStartOffset = viewOffset
  e.preventDefault()
}

function onDragMove(e: MouseEvent) {
  if (!isDragging) return
  const dx = Math.abs(e.clientX - dragStartX)
  if (dx > 3) hasDragged = true  // 移動超過 3px 才算拖曳
  const canvas = waveformCanvas.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const dxRatio = (e.clientX - dragStartX) / rect.width
  const viewWidth = 1 / zoomLevel
  viewOffset = Math.max(0, Math.min(1 - viewWidth, dragStartOffset - dxRatio * viewWidth))
  drawWaveform()
}

function onDragEnd() {
  isDragging = false
}

// ── Watch URL changes ─────────────────────────────────────────────────────
watch(() => props.previewUrl, async (url, oldUrl) => {
  // 存前一個檔案的播放位置
  if (oldUrl && audioRef.value && audioRef.value.currentTime > 0) {
    _timeCache.set(oldUrl, audioRef.value.currentTime)
  }

  waveformData = null
  playheadRatio = 0
  zoomLevel = 1
  viewOffset = 0
  isPlaying.value = false
  currentTimeStr.value = '0:00'
  durationStr.value = '0:00'
  decodeFailed.value = false
  const canvas = waveformCanvas.value
  if (canvas) canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height)
  if (url) await loadWaveform(url)
})

onUnmounted(() => {
  waveformData = null
})

</script>

<template>
  <div class="preview-display">
    <span v-if="previewUnsupported || decodeFailed" class="format-hint">
      <i class="bi bi-info-circle"></i> {{ $t('audio.preview_unsupported') }}
    </span>
    <div class="preview-body">
      <!-- 波形圖 -->
      <div v-if="previewUrl" class="waveform-wrap"
        @wheel.prevent="onWheelZoom"
        @mousedown="onDragStart"
        @mousemove="onDragMove"
        @mouseup="onDragEnd"
        @mouseleave="onDragEnd"
      >
        <canvas
          ref="waveformCanvas"
          class="waveform-canvas"
          width="1200"
          height="400"
          @click="onWaveformClick"
        />
      </div>

      <!-- 播放控制列 -->
      <div v-if="previewUrl" class="playback-controls">
        <button class="play-btn" @click="togglePlay">
          <i class="bi" :class="isPlaying ? 'bi-pause-fill' : 'bi-play-fill'"></i>
        </button>
        <span class="time-display">{{ currentTimeStr }} / {{ durationStr }}</span>
      </div>

      <!-- 隱藏的 audio 元素 -->
      <audio
        v-if="previewUrl"
        ref="audioRef"
        :src="previewUrl"
        @timeupdate="onTimeUpdate"
        @loadedmetadata="onLoadedMetadata"
        @ended="onEnded"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.preview-display {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.preview-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  min-height: 0;
  width: 100%;
  padding: 0;
}

.waveform-wrap {
  width: 100%;
  background: var(--panel-bg);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  user-select: none;

  &:hover { background: var(--panel-bg-hover); }
}

.waveform-canvas {
  width: 100%;
  height: auto;
  display: block;
}

.playback-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.play-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: var(--panel-bg);
  color: var(--text-primary);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s ease;

  i { font-size: 1.1rem; }

  &:hover { background: var(--panel-bg-hover); }
  &:active { background: var(--panel-bg-active); }
}

.time-display {
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
}

.format-hint {
  position: absolute;
  top: 0.5rem;
  left: 1rem;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  pointer-events: none;
  z-index: 5;
}
</style>
