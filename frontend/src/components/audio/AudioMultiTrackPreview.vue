<script setup lang="ts">
import { ref, reactive, watch, onMounted, onUnmounted, type Component, markRaw } from 'vue'
import { getApiBase } from '@/composables/useApi'
import IconVocals from '@/components/icons/IconVocals.vue'
import IconDrums from '@/components/icons/IconDrums.vue'
import IconBass from '@/components/icons/IconBass.vue'
import IconGuitar from '@/components/icons/IconGuitar.vue'
import IconPiano from '@/components/icons/IconPiano.vue'

interface StemDef {
  name: string
  fileId: string
  color: string
  path?: string
}

const props = defineProps<{
  stems: Array<StemDef>
}>()

// ── Icon mapping ────────────────────────────────────────────────────────────
const stemIconComponents: Record<string, Component> = {
  vocals: markRaw(IconVocals),
  drums: markRaw(IconDrums),
  bass: markRaw(IconBass),
  guitar: markRaw(IconGuitar),
  piano: markRaw(IconPiano),
}

function getStemIcon(name: string): string {
  // fallback for stems without custom SVG icon
  return name.toLowerCase() === 'other' ? 'bi-soundwave' : ''
}

function getStemIconComponent(name: string): Component | null {
  return stemIconComponents[name.toLowerCase()] ?? null
}

// ── Stem runtime state ──────────────────────────────────────────────────────
interface StemState {
  name: string
  fileId: string
  color: string
  waveformData: Float32Array | null
  audioBuffer: AudioBuffer | null
  gain: number       // 0-1
  muted: boolean
  loading: boolean
  error: boolean
}

const stemStates = reactive<StemState[]>([])

// ── Master volume ───────────────────────────────────────────────────────────
const masterVolume = ref(100)
const masterMuted = ref(false)
let baseScale: number | null = null  // 固定在初始載入時的 scale
let _pixelCacheKey = ''
let _pixelCache: Array<{ min: Float64Array; max: Float64Array }> = []

// ── Canvas & playback refs ──────────────────────────────────────────────────
const waveformCanvas = ref<HTMLCanvasElement | null>(null)
let audioCtx: AudioContext | null = null
let sourceNodes: AudioBufferSourceNode[] = []
let gainNodes: GainNode[] = []

const isPlaying = ref(false)
const currentTimeStr = ref('0:00')
const durationStr = ref('0:00')
let totalDuration = 0
let playheadRatio = 0
let startTimestamp = 0   // audioCtx.currentTime when playback started
let pauseOffset = 0      // seconds into audio when paused
let animFrameId = 0

// ── Zoom & Pan state ────────────────────────────────────────────────────────
let zoomLevel = 1
let viewOffset = 0
let isDragging = false
let hasDragged = false
let dragStartX = 0
let dragStartOffset = 0

// ── Vertical fader drag state ───────────────────────────────────────────────
let activeFaderIndex: number | null = null
let activeFaderIsMaster = false
let activeFaderTrackRect: DOMRect | null = null

function onFaderMouseDown(index: number, isMaster: boolean, e: MouseEvent) {
  e.preventDefault()
  activeFaderIndex = index
  activeFaderIsMaster = isMaster
  const track = (e.currentTarget as HTMLElement).querySelector('.v-fader-track') as HTMLElement
  if (!track) return
  activeFaderTrackRect = track.getBoundingClientRect()
  window.addEventListener('mousemove', onFaderMouseMove)
  window.addEventListener('mouseup', onFaderMouseUp)
}

function onFaderMouseMove(e: MouseEvent) {
  if (activeFaderTrackRect === null) return
  const rect = activeFaderTrackRect
  const y = e.clientY
  const ratio = 1 - Math.max(0, Math.min(1, (y - rect.top) / rect.height))
  const value = Math.round(ratio * 100)

  if (activeFaderIsMaster) {
    const delta = (value - masterVolume.value) / 100
    masterVolume.value = value
    // 所有 stem fader 跟著移動
    for (const st of stemStates) {
      if (!st.muted) {
        st.gain = Math.max(0, Math.min(1, st.gain + delta))
      }
    }
    updateAllGainNodes()
    drawWaveform()
  } else if (activeFaderIndex !== null) {
    stemStates[activeFaderIndex].gain = value / 100
    updateGainNode(activeFaderIndex)
    drawWaveform()
  }
}

function onFaderMouseUp() {
  activeFaderIndex = null
  activeFaderIsMaster = false
  activeFaderTrackRect = null
  window.removeEventListener('mousemove', onFaderMouseMove)
  window.removeEventListener('mouseup', onFaderMouseUp)
}

// ── Load all stems ──────────────────────────────────────────────────────────
async function loadStems() {
  stemStates.length = 0
  for (const stem of props.stems) {
    stemStates.push({
      name: stem.name,
      fileId: stem.fileId,
      color: stem.color,
      waveformData: null,
      audioBuffer: null,
      gain: 1,
      muted: false,
      loading: true,
      error: false,
    })
  }

  // 並行載入所有 stem（本地讀取 ~130ms/stem，不會卡 UI）
  await Promise.all(stemStates.map(async (st) => {
    try {
      let arrayBuffer: ArrayBuffer

      // 優先本地讀取（Electron），fallback 到 HTTP
      const stemDef = props.stems.find(s => s.fileId === st.fileId)
      if (stemDef?.path && window.electron?.readLocalFile) {
        const buffer = await window.electron.readLocalFile(stemDef.path)
        arrayBuffer = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength)
      } else {
        const resp = await fetch(getApiBase() + '/files/' + st.fileId + '/download')
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        arrayBuffer = await resp.arrayBuffer()
      }

      const decodeCtx = new AudioContext()
      const audioBuffer = await decodeCtx.decodeAudioData(arrayBuffer)
      await decodeCtx.close()

      // Mix down to mono
      const nCh = audioBuffer.numberOfChannels
      const len = audioBuffer.length
      const mono = new Float32Array(len)
      for (let c = 0; c < nCh; c++) {
        const ch = audioBuffer.getChannelData(c)
        for (let i = 0; i < len; i++) mono[i] += ch[i] / nCh
      }

      st.audioBuffer = audioBuffer
      st.waveformData = mono
      if (audioBuffer.duration > totalDuration) {
        totalDuration = audioBuffer.duration
        durationStr.value = formatTime(totalDuration)
      }
    } catch (e) {
      console.warn(`Failed to load stem "${st.name}":`, e)
      st.error = true
    } finally {
      st.loading = false
    }
  }))

  // 全部載完後計算 baseScale 並繪製
  baseScale = null
  _pixelCacheKey = ''
  drawWaveform()
}

// ── Hex to RGBA helper ──────────────────────────────────────────────────────
function hexToRgba(hex: string, alpha: number): string {
  // Handle rgb(...) format from getComputedStyle
  const rgbMatch = hex.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/)
  if (rgbMatch) return `rgba(${rgbMatch[1]}, ${rgbMatch[2]}, ${rgbMatch[3]}, ${alpha})`
  // Handle #hex format
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

// ── Format time ─────────────────────────────────────────────────────────────
function formatTime(s: number, showMs = false): string {
  if (!isFinite(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  const base = `${m}:${sec.toString().padStart(2, '0')}`
  if (!showMs) return base
  const ms = Math.round((s % 1) * 10)
  return `${base}.${ms}`
}

// ── Effective gain (stem * master) ──────────────────────────────────────────
function effectiveGain(st: StemState): number {
  if (st.muted || masterMuted.value) return 0
  return st.gain
}

// ── Draw waveform ───────────────────────────────────────────────────────────
function drawWaveform() {
  const canvas = waveformCanvas.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')!
  const W = canvas.width
  const H = canvas.height

  const viewWidth = 1 / zoomLevel
  const startRatio = viewOffset
  const endRatio = Math.min(startRatio + viewWidth, 1)

  // Playhead x position
  const phRatioInView = (playheadRatio - startRatio) / viewWidth
  const ph = Math.round(phRatioInView * W)

  ctx.clearRect(0, 0, W, H)

  // Read theme colors from CSS variables
  const cs = getComputedStyle(canvas)
  const textPrimary = cs.getPropertyValue('--text-primary').trim() || '#ffffff'

  const waveH = H - 24
  const midY = waveH / 2

  // Centre baseline
  ctx.fillStyle = hexToRgba(textPrimary, 0.05)
  ctx.fillRect(0, midY, W, 1)

  // ── Rebuild raw pixel cache when zoom/pan/size changes ──
  const cacheKey = `${W}:${startRatio.toFixed(6)}:${endRatio.toFixed(6)}`
  if (cacheKey !== _pixelCacheKey) {
    _pixelCacheKey = cacheKey
    _pixelCache = stemStates.map(st => {
      const px = { min: new Float64Array(W), max: new Float64Array(W) }
      if (!st.waveformData) return px
      const data = st.waveformData
      const startSample = Math.floor(startRatio * data.length)
      const endSample = Math.ceil(endRatio * data.length)
      const visibleSamples = endSample - startSample
      const step = Math.max(1, Math.ceil(visibleSamples / W))
      for (let x = 0; x < W; x++) {
        const sampleStart = startSample + Math.floor(x * visibleSamples / W)
        let mn = 0, mx = 0
        for (let j = 0; j < step; j++) {
          const v = data[sampleStart + j] ?? 0
          if (v < mn) mn = v
          if (v > mx) mx = v
        }
        px.min[x] = mn
        px.max[x] = mx
      }
      return px
    })

    // Calculate baseScale on first build (all stems gain=1)
    if (baseScale === null) {
      let initPeak = 0
      for (let x = 0; x < W; x++) {
        let sumMin = 0, sumMax = 0
        for (const px of _pixelCache) {
          sumMin += px.min[x]
          sumMax += px.max[x]
        }
        if (Math.abs(sumMax) > initPeak) initPeak = Math.abs(sumMax)
        if (Math.abs(sumMin) > initPeak) initPeak = Math.abs(sumMin)
      }
      baseScale = initPeak > 0.001 ? 0.95 / initPeak : 1
    }
  }

  const scale = baseScale ?? 1
  const halfH = waveH / 2

  // ── Draw stems + accumulate mix (fast: only multiply cached values by gain) ──
  const mixMin = new Float64Array(W)
  const mixMax = new Float64Array(W)

  for (let i = 0; i < stemStates.length; i++) {
    const st = stemStates[i]
    const px = _pixelCache[i]
    if (!px || st.muted || masterMuted.value) continue
    const gain = effectiveGain(st)

    ctx.fillStyle = st.color
    for (let x = 0; x < W; x++) {
      const mn = px.min[x] * gain
      const mx = px.max[x] * gain
      mixMin[x] += mn
      mixMax[x] += mx
      const top = midY - mx * scale * halfH
      const bot = midY - mn * scale * halfH
      ctx.fillRect(x, top, 1, Math.max(1, bot - top))
    }
  }

  // ── Draw mixed waveform ──
  ctx.fillStyle = hexToRgba(textPrimary, 0.15)
  for (let x = 0; x < W; x++) {
    const top = midY - mixMax[x] * scale * halfH
    const bot = midY - mixMin[x] * scale * halfH
    if (bot - top > 0.5) ctx.fillRect(x, top, 1, bot - top)
  }

  // Playhead line
  if (ph >= 0 && ph <= W) {
    ctx.fillStyle = hexToRgba(textPrimary, 0.9)
    ctx.fillRect(ph, 0, 1, waveH)
  }

  // ── Time axis ──
  if (totalDuration <= 0) return

  const timelineH = 24
  const timelineY = H - timelineH

  ctx.fillStyle = 'rgba(0, 0, 0, 0.3)'
  ctx.fillRect(0, timelineY, W, timelineH)

  const startTime = startRatio * totalDuration
  const endTime = endRatio * totalDuration
  const visibleDuration = endTime - startTime

  const intervals = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
  const minPixelGap = 60
  const targetInterval = visibleDuration / (W / minPixelGap)
  const tickInterval = intervals.find(i => i >= targetInterval) ?? 600

  ctx.font = '18px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'

  const firstTick = Math.ceil(startTime / tickInterval) * tickInterval
  for (let t = firstTick; t <= endTime; t += tickInterval) {
    const x = ((t - startTime) / visibleDuration) * W

    ctx.fillStyle = hexToRgba(textPrimary, 0.3)
    ctx.fillRect(Math.round(x), timelineY, 1, 6)

    ctx.fillStyle = hexToRgba(textPrimary, 0.5)
    const label = formatTime(t, tickInterval < 1)
    ctx.fillText(label, x, timelineY + 7)
  }
}

// ── Web Audio playback ──────────────────────────────────────────────────────
function ensureAudioContext() {
  if (!audioCtx || audioCtx.state === 'closed') {
    audioCtx = new AudioContext()
  }
  return audioCtx
}

function createSourceNodes(offset: number) {
  const ctx = ensureAudioContext()
  // Cleanup old
  stopSourceNodes()

  sourceNodes = []
  gainNodes = []

  for (const st of stemStates) {
    if (!st.audioBuffer) continue
    const source = ctx.createBufferSource()
    source.buffer = st.audioBuffer
    const gain = ctx.createGain()
    gain.gain.value = effectiveGain(st)
    source.connect(gain)
    gain.connect(ctx.destination)
    sourceNodes.push(source)
    gainNodes.push(gain)
  }

  // Start all in sync
  const startTime = ctx.currentTime
  for (const src of sourceNodes) {
    src.start(0, offset)
  }
  startTimestamp = startTime
  pauseOffset = offset

  // Handle ended on first source
  if (sourceNodes.length > 0) {
    sourceNodes[0].onended = () => {
      if (isPlaying.value) {
        isPlaying.value = false
        pauseOffset = 0
        playheadRatio = 0
        cancelAnimationFrame(animFrameId)
        currentTimeStr.value = formatTime(0)
        drawWaveform()
      }
    }
  }
}

function stopSourceNodes() {
  for (const src of sourceNodes) {
    src.onended = null  // 防止 stop() 觸發 onended 干擾狀態
    try { src.stop() } catch { /* already stopped */ }
    try { src.disconnect() } catch { /* ok */ }
  }
  for (const g of gainNodes) {
    try { g.disconnect() } catch { /* ok */ }
  }
  sourceNodes = []
  gainNodes = []
}

function togglePlay() {
  if (isPlaying.value) {
    // Pause
    const ctx = ensureAudioContext()
    const elapsed = ctx.currentTime - startTimestamp
    pauseOffset = pauseOffset + elapsed
    if (pauseOffset >= totalDuration) pauseOffset = 0
    stopSourceNodes()
    isPlaying.value = false
    cancelAnimationFrame(animFrameId)
  } else {
    // Play
    if (pauseOffset >= totalDuration) pauseOffset = 0
    createSourceNodes(pauseOffset)
    isPlaying.value = true
    updatePlayhead()
  }
}

function updatePlayhead() {
  if (!isPlaying.value || !audioCtx) return
  const elapsed = audioCtx.currentTime - startTimestamp
  const currentTime = pauseOffset + elapsed
  if (currentTime >= totalDuration) {
    playheadRatio = 1
    currentTimeStr.value = formatTime(totalDuration)
    drawWaveform()
    return
  }
  playheadRatio = currentTime / totalDuration
  currentTimeStr.value = formatTime(currentTime)
  drawWaveform()
  animFrameId = requestAnimationFrame(updatePlayhead)
}

// ── Seek on waveform click ──────────────────────────────────────────────────
function onWaveformClick(e: MouseEvent) {
  if (hasDragged) { hasDragged = false; return }
  const canvas = waveformCanvas.value
  if (!canvas || totalDuration <= 0) return
  const rect = canvas.getBoundingClientRect()
  const clickRatio = (e.clientX - rect.left) / rect.width
  const viewWidth = 1 / zoomLevel
  const ratio = Math.max(0, Math.min(1, viewOffset + clickRatio * viewWidth))

  const wasPlaying = isPlaying.value
  if (wasPlaying) {
    stopSourceNodes()
    cancelAnimationFrame(animFrameId)
  }

  pauseOffset = ratio * totalDuration
  playheadRatio = ratio
  currentTimeStr.value = formatTime(pauseOffset)
  drawWaveform()

  if (wasPlaying) {
    createSourceNodes(pauseOffset)
    isPlaying.value = true
    updatePlayhead()
  }
}

// ── Zoom (scroll wheel) ─────────────────────────────────────────────────────
function onWheelZoom(e: WheelEvent) {
  e.preventDefault()
  const canvas = waveformCanvas.value
  if (!canvas) return

  const rect = canvas.getBoundingClientRect()
  const cursorRatio = (e.clientX - rect.left) / rect.width
  const viewWidth = 1 / zoomLevel
  const cursorInTrack = viewOffset + cursorRatio * viewWidth

  const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2
  zoomLevel = Math.max(1, Math.min(200, zoomLevel * factor))

  const newViewWidth = 1 / zoomLevel
  viewOffset = Math.max(0, Math.min(1 - newViewWidth, cursorInTrack - cursorRatio * newViewWidth))

  drawWaveform()
}

// ── Pan (drag) ──────────────────────────────────────────────────────────────
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
  if (dx > 3) hasDragged = true
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

// ── Gain/Mute changes ───────────────────────────────────────────────────────
function toggleMute(index: number) {
  const st = stemStates[index]
  st.muted = !st.muted
  updateGainNode(index)
  drawWaveform()
}

function toggleMasterMute() {
  masterMuted.value = !masterMuted.value
  updateAllGainNodes()
  drawWaveform()
}

function updateGainNode(index: number) {
  // gainNodes maps to stemStates entries that have audioBuffer
  let gi = 0
  for (let i = 0; i < stemStates.length; i++) {
    if (!stemStates[i].audioBuffer) continue
    if (i === index) {
      if (gi < gainNodes.length) {
        gainNodes[gi].gain.value = effectiveGain(stemStates[i])
      }
      return
    }
    gi++
  }
}

function updateAllGainNodes() {
  let gi = 0
  for (let i = 0; i < stemStates.length; i++) {
    if (!stemStates[i].audioBuffer) continue
    if (gi < gainNodes.length) {
      gainNodes[gi].gain.value = effectiveGain(stemStates[i])
    }
    gi++
  }
}

// ── Lifecycle ───────────────────────────────────────────────────────────────
watch(() => props.stems, () => {
  cleanup()
  baseScale = null
  _pixelCacheKey = ''
  _pixelCache = []
  totalDuration = 0
  playheadRatio = 0
  pauseOffset = 0
  zoomLevel = 1
  viewOffset = 0
  isPlaying.value = false
  currentTimeStr.value = '0:00'
  durationStr.value = '0:00'
  masterVolume.value = 80
  masterMuted.value = false
  loadStems()
}, { deep: true })

onMounted(() => {
  loadStems()
})

function cleanup() {
  cancelAnimationFrame(animFrameId)
  stopSourceNodes()
  if (audioCtx && audioCtx.state !== 'closed') {
    audioCtx.close().catch(() => {})
  }
  audioCtx = null
}

onUnmounted(() => {
  cleanup()
  window.removeEventListener('mousemove', onFaderMouseMove)
  window.removeEventListener('mouseup', onFaderMouseUp)
})
</script>

<template>
  <div class="stem-player">
    <!-- Waveform canvas -->
    <div class="waveform-section"
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

    <!-- Fader section -->
    <div class="faders-section">
      <!-- Master fader -->
      <div class="fader-column" :class="{ 'is-muted': masterMuted }">
        <i class="bi bi-speaker-fill fader-icon" style="color: var(--text-primary)"></i>
        <span class="fader-label">Master</span>

        <div class="v-fader" @mousedown="onFaderMouseDown(-1, true, $event)">
          <div class="v-fader-track">
            <div
              class="v-fader-fill"
              :style="{ height: masterVolume + '%', background: 'var(--text-primary)' }"
            ></div>
            <div
              class="v-fader-thumb"
              :style="{ bottom: masterVolume + '%' }"
            ></div>
          </div>
        </div>

        <span class="fader-value">{{ masterVolume }}%</span>

        <button class="mute-btn" @click="toggleMasterMute">
          <i class="bi" :class="masterMuted ? 'bi-volume-mute-fill' : 'bi-volume-up-fill'"></i>
        </button>
      </div>

      <!-- Divider -->
      <div class="fader-divider"></div>

      <!-- Stem faders -->
      <div
        v-for="(st, idx) in stemStates"
        :key="st.fileId"
        class="fader-column"
        :class="{ 'is-muted': st.muted || masterMuted, 'is-loading': st.loading, 'is-error': st.error }"
      >
        <component
          v-if="getStemIconComponent(st.name)"
          :is="getStemIconComponent(st.name)"
          :size="28"
          :color="st.color"
          class="fader-icon"
        />
        <i v-else class="bi fader-icon" :class="getStemIcon(st.name)" :style="{ color: st.color }"></i>
        <span class="fader-label">{{ st.name }}</span>

        <template v-if="st.loading">
          <div class="fader-status">
            <i class="bi bi-arrow-repeat spin"></i>
          </div>
        </template>
        <template v-else-if="st.error">
          <div class="fader-status fader-error">
            <i class="bi bi-exclamation-triangle"></i>
          </div>
        </template>
        <template v-else>
          <div class="v-fader" @mousedown="onFaderMouseDown(idx, false, $event)">
            <div class="v-fader-track">
              <div
                class="v-fader-fill"
                :style="{ height: Math.round(st.gain * 100) + '%', background: st.color }"
              ></div>
              <div
                class="v-fader-thumb"
                :style="{ bottom: Math.round(st.gain * 100) + '%' }"
              ></div>
            </div>
          </div>

          <span class="fader-value">
            {{ st.muted ? 'muted' : Math.round(st.gain * 100) + '%' }}
          </span>

          <button class="mute-btn" @click="toggleMute(idx)">
            <i class="bi" :class="st.muted ? 'bi-volume-mute-fill' : 'bi-volume-up-fill'"></i>
          </button>
        </template>
      </div>
    </div>

    <!-- Transport bar -->
    <div class="transport-bar">
      <button class="play-btn" @click="togglePlay">
        <i class="bi" :class="isPlaying ? 'bi-pause-fill' : 'bi-play-fill'"></i>
      </button>
      <span class="time-display">{{ currentTimeStr }} / {{ durationStr }}</span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.stem-player {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0;
  border-radius: 12px;
  overflow: hidden;
  background: var(--panel-bg);
}

// ── Waveform section ──────────────────────────────────────────────────────
.waveform-section {
  width: 100%;
  overflow: hidden;
  cursor: pointer;
  user-select: none;
}

.waveform-canvas {
  width: 100%;
  height: auto;
  display: block;
}

// ── Fader section ─────────────────────────────────────────────────────────
.faders-section {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  overflow-x: auto;
  border-top: 1px solid var(--panel-border);
}

.fader-divider {
  width: 1px;
  height: 200px;
  background: var(--panel-border);
  flex-shrink: 0;
  align-self: center;
  margin: 0 0.25rem;
}

.fader-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  width: 64px;
  min-width: 64px;
  transition: opacity 0.15s ease;

  &.is-muted {
    opacity: 0.45;
  }

  &.is-loading,
  &.is-error {
    opacity: 0.5;
  }
}

.fader-icon {
  font-size: 1.2rem;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
}

.fader-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: capitalize;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  text-align: center;
}

.fader-status {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 1rem;
}

.fader-error {
  color: var(--color-danger);
}

.fader-value {
  font-size: 0.7rem;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

// ── Custom vertical fader ─────────────────────────────────────────────────
.v-fader {
  width: 32px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  touch-action: none;
}

.v-fader-track {
  position: relative;
  width: 4px;
  height: 100%;
  background: var(--panel-bg);
  border-radius: 2px;
  overflow: visible;
}

.v-fader-fill {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  border-radius: 2px;
  opacity: 0.6;
  transition: none;
}

.v-fader-thumb {
  position: absolute;
  left: 50%;
  width: 14px;
  height: 14px;
  background: var(--text-primary);
  border-radius: 50%;
  transform: translate(-50%, 50%);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  transition: none;
  pointer-events: none;
}

// ── Mute button ───────────────────────────────────────────────────────────
.mute-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 0.85rem;
  transition: background 0.15s ease, color 0.15s ease;
  padding: 0;

  &:hover {
    background: var(--input-bg);
    color: var(--text-primary);
  }

  &:active {
    background: var(--input-bg-focus);
  }
}

// ── Transport bar ─────────────────────────────────────────────────────────
.transport-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  border-top: 1px solid var(--panel-border);
}

.play-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: var(--input-bg);
  color: var(--text-primary);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s ease;
  padding: 0;

  i { font-size: 1.1rem; }

  &:hover { background: var(--panel-bg-hover); }
  &:active { background: var(--panel-bg-active); }
}

.time-display {
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
}

// ── Spinner ───────────────────────────────────────────────────────────────
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin {
  display: inline-block;
  animation: spin 1s linear infinite;
}
</style>
