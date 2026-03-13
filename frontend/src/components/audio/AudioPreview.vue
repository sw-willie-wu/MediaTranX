<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps<{
  previewUrl: string | null
  file: File | null
}>()

// ── Refs ──────────────────────────────────────────────────────────────────
const audioRef       = ref<HTMLAudioElement | null>(null)
const waveformCanvas = ref<HTMLCanvasElement | null>(null)

// ── Waveform state ────────────────────────────────────────────────────────
let waveformData: Float32Array | null = null
let playheadRatio = 0

async function loadWaveform(url: string) {
  const canvas = waveformCanvas.value
  if (!canvas) return
  waveformData = null
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
    playheadRatio = 0
    drawWaveform()
  } catch (e) {
    console.warn('Waveform decode failed:', e)
  }
}

function drawWaveform() {
  const canvas = waveformCanvas.value
  if (!canvas || !waveformData) return

  const ctx  = canvas.getContext('2d')!
  const W    = canvas.width
  const H    = canvas.height
  const data = waveformData
  const step = Math.max(1, Math.ceil(data.length / W))
  const ph   = Math.round(playheadRatio * W)

  ctx.clearRect(0, 0, W, H)

  // centre baseline
  ctx.fillStyle = 'rgba(255,255,255,0.05)'
  ctx.fillRect(0, H / 2, W, 1)

  for (let x = 0; x < W; x++) {
    let min = 0, max = 0
    for (let j = 0; j < step; j++) {
      const v = data[x * step + j] ?? 0
      if (v < min) min = v
      if (v > max) max = v
    }
    const amp  = (max - min) / 2
    const barH = Math.max(1, amp * H * 0.88)
    const y    = H / 2 - barH / 2

    ctx.fillStyle = x < ph
      ? 'rgba(160, 130, 230, 0.92)'
      : 'rgba(110, 90, 160, 0.45)'
    ctx.fillRect(x, y, 1, barH)
  }

  // playhead line
  if (ph > 0 && ph < W) {
    ctx.fillStyle = 'rgba(230, 210, 255, 0.9)'
    ctx.fillRect(ph, 0, 1, H)
  }
}

// ── Audio events ──────────────────────────────────────────────────────────
function onTimeUpdate() {
  const el = audioRef.value
  if (!el || !el.duration) return
  playheadRatio = el.currentTime / el.duration
  drawWaveform()
}

function onEnded() {
  playheadRatio = 1
  drawWaveform()
}

// ── Seek on waveform click ────────────────────────────────────────────────
function onWaveformClick(e: MouseEvent) {
  const canvas = waveformCanvas.value
  const el = audioRef.value
  if (!canvas || !el || !el.duration) return
  const rect = canvas.getBoundingClientRect()
  const ratio = (e.clientX - rect.left) / rect.width
  el.currentTime = ratio * el.duration
  playheadRatio = ratio
  drawWaveform()
}

// ── Watch URL changes ─────────────────────────────────────────────────────
watch(() => props.previewUrl, async (url) => {
  waveformData = null
  playheadRatio = 0
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
    <div class="preview-body">
      <div class="audio-card">
        <!-- 圖示 + 檔名 -->
        <div class="audio-header">
          <div class="audio-icon">
            <i class="bi bi-music-note-beamed"></i>
          </div>
          <p class="filename">{{ file?.name }}</p>
        </div>

        <!-- 波形圖 -->
        <div v-if="previewUrl" class="waveform-wrap">
          <canvas
            ref="waveformCanvas"
            class="waveform-canvas"
            width="600"
            height="80"
            @click="onWaveformClick"
          />
        </div>

        <!-- 播放器 -->
        <audio
          v-if="previewUrl"
          ref="audioRef"
          :src="previewUrl"
          controls
          class="audio-player"
          @timeupdate="onTimeUpdate"
          @ended="onEnded"
        />
      </div>
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
  align-items: center;
  justify-content: center;
  min-height: 0;
}

.audio-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.5rem 1.75rem;
  background: var(--input-bg);
  border-radius: 16px;
  width: min(600px, 90%);
}

.audio-header {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.audio-icon {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--color-warning) 0%, #d97706 100%);
  border-radius: 10px;

  i { font-size: 1.5rem; color: white; }
}

.filename {
  color: var(--text-primary);
  font-size: 0.88rem;
  margin: 0;
  word-break: break-all;
  flex: 1;
}

.waveform-wrap {
  background: rgba(0, 0, 0, 0.28);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;

  &:hover { background: rgba(0, 0, 0, 0.35); }
}

.waveform-canvas {
  width: 100%;
  height: auto;
  display: block;
}

.audio-player {
  width: 100%;
}
</style>
