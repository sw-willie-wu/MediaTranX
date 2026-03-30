<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { MidiNote } from '@/composables/useMidiEditor'

const props = defineProps<{
  notes: MidiNote[]
  selectedNoteIds: Set<string>
  trackColor: string
  scrollX: number
  zoomX: number
  gridSize: number
}>()

const emit = defineEmits<{
  'update-velocity': [ids: string[], velocity: number]
}>()

const containerRef = ref<HTMLDivElement>()
const canvasRef = ref<HTMLCanvasElement>()

const PIANO_KEY_WIDTH = 48
const MAX_VELOCITY = 127
const BAR_MIN_WIDTH = 4

// ── Resize handling ──

let resizeObserver: ResizeObserver | null = null
let canvasW = 0
let canvasH = 0

function syncCanvasSize() {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !container) return
  const dpr = window.devicePixelRatio || 1
  const rect = container.getBoundingClientRect()
  canvasW = rect.width
  canvasH = rect.height
  canvas.width = canvasW * dpr
  canvas.height = canvasH * dpr
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  draw()
}

// ── Drawing ──

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, canvasW, canvasH)

  const isLight = document.documentElement.getAttribute('data-theme') === 'light'

  // Subtle background
  ctx.fillStyle = isLight ? 'rgba(0, 0, 0, 0.04)' : 'rgba(10, 10, 25, 0.25)'
  ctx.fillRect(0, 0, canvasW, canvasH)

  // "Vel" label
  ctx.fillStyle = isLight ? '#444' : '#bbb'
  ctx.font = 'bold 12px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('Vel', PIANO_KEY_WIDTH / 2, canvasH / 2)

  // Horizontal guide lines at velocity 32, 64, 96
  const barArea = canvasH - 4
  ctx.setLineDash([4, 4])
  ctx.strokeStyle = isLight ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.08)'
  ctx.lineWidth = 1
  for (const v of [32, 64, 96]) {
    const y = canvasH - 2 - (v / MAX_VELOCITY) * barArea
    ctx.beginPath()
    ctx.moveTo(PIANO_KEY_WIDTH, y)
    ctx.lineTo(canvasW, y)
    ctx.stroke()
  }
  ctx.setLineDash([])

  // Draw velocity bars (fixed-width stems, not tied to note duration)
  const { notes, selectedNoteIds, trackColor, scrollX, zoomX } = props
  const stemW = Math.max(BAR_MIN_WIDTH, Math.min(10, props.gridSize * zoomX * 0.6))
  for (const note of notes) {
    const cx = PIANO_KEY_WIDTH + note.start * zoomX - scrollX + stemW / 2
    const x = cx - stemW / 2
    if (x + stemW < PIANO_KEY_WIDTH || x > canvasW) continue

    const h = Math.max(2, (note.velocity / MAX_VELOCITY) * barArea)
    const y = canvasH - 2 - h
    const selected = selectedNoteIds.has(note.id)

    ctx.fillStyle = selected ? lightenColor(trackColor, 0.35) : trackColor
    const r = Math.min(2, stemW / 2, h / 2)
    ctx.beginPath()
    ctx.roundRect(x, y, stemW, h, [r, r, 0, 0])
    ctx.fill()
  }
}

function lightenColor(hex: string, amount: number): string {
  const c = hex.replace('#', '')
  const r = Math.min(255, parseInt(c.substring(0, 2), 16) + 255 * amount)
  const g = Math.min(255, parseInt(c.substring(2, 4), 16) + 255 * amount)
  const b = Math.min(255, parseInt(c.substring(4, 6), 16) + 255 * amount)
  return `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`
}

// ── Mouse interaction ──

let dragging = false
let dragNoteId: string | null = null
let dragStartVelocity = 0

function hitTest(mx: number): MidiNote | null {
  const { notes, scrollX, zoomX, gridSize } = props
  const stemW = Math.max(BAR_MIN_WIDTH, Math.min(10, gridSize * zoomX * 0.6))
  const hitPad = Math.max(stemW, 6) // minimum clickable area
  for (let i = notes.length - 1; i >= 0; i--) {
    const note = notes[i]
    const cx = PIANO_KEY_WIDTH + note.start * zoomX - scrollX + stemW / 2
    if (mx >= cx - hitPad / 2 && mx <= cx + hitPad / 2) return note
  }
  return null
}

function yToVelocity(y: number): number {
  const barArea = canvasH - 4
  const v = ((canvasH - 2 - y) / barArea) * MAX_VELOCITY
  return Math.max(1, Math.min(MAX_VELOCITY, Math.round(v)))
}

function onMouseDown(e: MouseEvent) {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  const hit = hitTest(mx)
  if (!hit) return

  dragging = true
  dragNoteId = hit.id
  dragStartVelocity = hit.velocity

  const newVel = yToVelocity(my)
  emitVelocity(hit, newVel)

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e: MouseEvent) {
  if (!dragging) return
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const my = e.clientY - rect.top
  const newVel = yToVelocity(my)
  const note = props.notes.find((n) => n.id === dragNoteId)
  if (note) emitVelocity(note, newVel)
}

function onMouseUp() {
  dragging = false
  dragNoteId = null
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
}

function emitVelocity(note: MidiNote, newVel: number) {
  if (props.selectedNoteIds.has(note.id) && props.selectedNoteIds.size > 1) {
    const delta = newVel - note.velocity
    const ids = Array.from(props.selectedNoteIds)
    // For multi-select, emit the target velocity (parent handles relative logic)
    // We emit per-note clamped absolute velocity via delta from original
    const clampedVel = Math.max(1, Math.min(MAX_VELOCITY, dragStartVelocity + delta))
    emit('update-velocity', ids, clampedVel)
  } else {
    emit('update-velocity', [note.id], newVel)
  }
}

// ── Lifecycle ──

onMounted(() => {
  syncCanvasSize()
  resizeObserver = new ResizeObserver(syncCanvasSize)
  if (containerRef.value) resizeObserver.observe(containerRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
})

watch(
  () => [props.notes, props.selectedNoteIds, props.trackColor, props.scrollX, props.zoomX, props.gridSize],
  draw,
  { deep: true },
)
</script>

<template>
  <div class="midi-velocity-editor" ref="containerRef">
    <canvas ref="canvasRef" @mousedown="onMouseDown" />
  </div>
</template>

<style lang="scss">
.midi-velocity-editor {
  width: 100%;
  height: 80px;
  flex-shrink: 0;
  overflow: hidden;

  canvas {
    display: block;
    width: 100%;
    height: 100%;
  }
}
</style>
