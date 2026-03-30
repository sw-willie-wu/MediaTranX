<script setup lang="ts">
/**
 * MidiPianoRoll — Canvas-based piano roll editor
 *
 * Renders MIDI notes on a scrollable/zoomable grid with piano key labels,
 * bar rulers, and interactive editing (select, draw, erase).
 */
import { ref, watch, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import type { MidiTrack, ToolMode } from '@/composables/useMidiEditor'

// ── Props & Emits ──

const props = defineProps<{
  tracks: MidiTrack[]
  activeTrackIndex: number
  selectedNoteIds: Set<string>
  toolMode: ToolMode
  gridSize: number
  snapEnabled: boolean
  currentBeat: number
  isPlaying: boolean
  tempo: number
  timeSignature: [number, number]
}>()

const emit = defineEmits<{
  'add-note': [pitch: number, start: number, duration: number, velocity: number]
  'delete-notes': [ids: string[]]
  'move-notes': [ids: string[], deltaBeat: number, deltaPitch: number]
  'resize-notes': [ids: string[], newDuration: number]
  'select-notes': [ids: string[], addToSelection: boolean]
  'clear-selection': []
  'play-note': [pitch: number]
  'update-velocity': [ids: string[], velocity: number]
  'undo': []
  'redo': []
  'select-all': []
  'copy': []
  'paste': [beat: number]
  'duplicate': []
}>()

// ── Constants ──

const PIANO_KEY_WIDTH = 48
const BAR_RULER_HEIGHT = 24
const NOTE_HEIGHT = 14
const MIN_PITCH = 21   // A0
const MAX_PITCH = 108  // C8
const TOTAL_ROWS = MAX_PITCH - MIN_PITCH + 1

const RESIZE_HANDLE_PX = 6 // pixels from right edge to trigger resize

// Colors — theme-aware, semi-transparent to let the app gradient show through
const COLORS_DARK = {
  darkRow: 'rgba(10, 10, 25, 0.45)',
  lightRow: 'rgba(20, 20, 40, 0.0)',
  gridBeat: 'rgba(255,255,255,0.08)',
  gridBar: 'rgba(255,255,255,0.18)',
  gridSub: 'rgba(255,255,255,0.04)',
  pianoWhite: 'rgba(255,255,255,0.0)',
  pianoBlack: 'rgba(0,0,0,0.25)',
  pianoLabel: 'rgba(255,255,255,0.65)',
  pianoColumnBg: 'rgba(0, 0, 0, 0.0)',
  rulerBg: 'rgba(10, 10, 25, 0.55)',
  rulerText: 'rgba(255,255,255,0.5)',
  cursor: '#7c6fad',
  selectionBox: 'rgba(124,111,173,0.2)',
  selectionBorder: 'rgba(124,111,173,0.7)',
  selectedBorder: '#a89cc8',
}

const COLORS_LIGHT = {
  darkRow: 'rgba(0, 0, 0, 0.08)',
  lightRow: 'rgba(0, 0, 0, 0.0)',
  gridBeat: 'rgba(0,0,0,0.1)',
  gridBar: 'rgba(0,0,0,0.2)',
  gridSub: 'rgba(0,0,0,0.04)',
  pianoWhite: 'rgba(255,255,255,0.0)',
  pianoBlack: 'rgba(0,0,0,0.15)',
  pianoLabel: 'rgba(0,0,0,0.7)',
  pianoColumnBg: 'rgba(0, 0, 0, 0.0)',
  rulerBg: 'rgba(255, 255, 255, 0.5)',
  rulerText: 'rgba(0,0,0,0.5)',
  cursor: '#6b5fa0',
  selectionBox: 'rgba(107,95,160,0.15)',
  selectionBorder: 'rgba(107,95,160,0.6)',
  selectedBorder: '#6b5fa0',
}

function getColors() {
  const theme = document.documentElement.getAttribute('data-theme')
  return theme === 'light' ? COLORS_LIGHT : COLORS_DARK
}

// Which pitches are black keys (relative to octave)
const BLACK_KEY_OFFSETS = new Set([1, 3, 6, 8, 10])

function isBlackKey(pitch: number): boolean {
  return BLACK_KEY_OFFSETS.has(pitch % 12)
}

function pitchName(pitch: number): string {
  const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const octave = Math.floor(pitch / 12) - 1
  return `${names[pitch % 12]}${octave}`
}

// ── Refs ──

const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)

const scrollX = ref(0)
const scrollY = ref(0)
const zoomX = ref(80)  // pixels per beat
const zoomY = ref(1)

const needsRedraw = ref(true)
let animFrameId = 0

// ── Drag state ──

const dragState = ref<{
  type: 'none' | 'move' | 'resize' | 'select-box' | 'scroll' | 'draw'
  startX: number
  startY: number
  startBeat: number
  startPitch: number
  currentX: number
  currentY: number
  noteId?: string
  originalNotes?: { id: string; start: number; pitch: number; duration: number }[]
} | null>(null)

// ── Computed ──

const activeTrack = computed<MidiTrack | null>(() => {
  const idx = props.activeTrackIndex
  if (idx >= 0 && idx < props.tracks.length) {
    return props.tracks[idx]
  }
  return null
})

const beatsPerBar = computed(() => props.timeSignature[0])

const rowHeight = computed(() => NOTE_HEIGHT * zoomY.value)

// ── Coordinate conversions ──

function beatToX(beat: number): number {
  return PIANO_KEY_WIDTH + beat * zoomX.value - scrollX.value
}

function xToBeat(x: number): number {
  return (x - PIANO_KEY_WIDTH + scrollX.value) / zoomX.value
}

function pitchToY(pitch: number): number {
  return BAR_RULER_HEIGHT + (MAX_PITCH - pitch) * rowHeight.value - scrollY.value
}

function yToPitch(y: number): number {
  return MAX_PITCH - Math.floor((y - BAR_RULER_HEIGHT + scrollY.value) / rowHeight.value)
}

function snapBeat(beat: number): number {
  if (!props.snapEnabled) return beat
  const gs = props.gridSize
  return Math.round(beat / gs) * gs
}

const NOTE_RADIUS = 5

function fillRoundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  if (w < r * 2) r = w / 2
  if (h < r * 2) r = h / 2
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, r)
  ctx.fill()
}

function strokeRoundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  if (w < r * 2) r = w / 2
  if (h < r * 2) r = h / 2
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, r)
  ctx.stroke()
}

// ── Hit testing ──

function hitTestNote(
  x: number,
  y: number,
): { noteId: string; edge: 'body' | 'right' } | null {
  const track = activeTrack.value
  if (!track) return null

  // Iterate in reverse so topmost (last drawn) notes are hit first
  for (let i = track.notes.length - 1; i >= 0; i--) {
    const note = track.notes[i]
    const nx = beatToX(note.start)
    const ny = pitchToY(note.pitch)
    const nw = note.duration * zoomX.value
    const nh = rowHeight.value

    if (x >= nx && x <= nx + nw && y >= ny && y <= ny + nh) {
      if (x >= nx + nw - RESIZE_HANDLE_PX) {
        return { noteId: note.id, edge: 'right' }
      }
      return { noteId: note.id, edge: 'body' }
    }
  }
  return null
}

// ── Drawing ──

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  // Use logical (CSS) pixel dimensions, not the DPR-scaled canvas buffer size.
  // The DPR transform is applied via setTransform in updateCanvasSize, so all
  // draw calls operate in CSS-pixel coordinate space.
  const dpr = window.devicePixelRatio || 1
  const W = canvas.width / dpr
  const H = canvas.height / dpr
  const rh = rowHeight.value
  const bpb = beatsPerBar.value

  if (W === 0 || H === 0) return // container not yet laid out

  const c = getColors()

  // 1. Clear — use raw canvas dimensions to guarantee full buffer clear
  ctx.save()
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.restore()

  // 2. Background rows
  for (let pitch = MAX_PITCH; pitch >= MIN_PITCH; pitch--) {
    const y = pitchToY(pitch)
    if (y + rh < BAR_RULER_HEIGHT || y > H) continue
    ctx.fillStyle = isBlackKey(pitch) ? c.darkRow : c.lightRow
    ctx.fillRect(PIANO_KEY_WIDTH, y, W - PIANO_KEY_WIDTH, rh)
  }

  // 3. Grid lines
  const firstBeat = Math.max(0, Math.floor(xToBeat(PIANO_KEY_WIDTH)))
  const lastBeat = Math.ceil(xToBeat(W))

  // Sub-beat grid lines (gridSize)
  if (props.gridSize < 1) {
    const gs = props.gridSize
    const firstSub = Math.max(0, Math.floor(xToBeat(PIANO_KEY_WIDTH) / gs) * gs)
    ctx.strokeStyle = c.gridSub
    ctx.lineWidth = 1
    for (let b = firstSub; b <= lastBeat; b += gs) {
      // Skip full beats (drawn separately)
      if (Math.abs(b - Math.round(b)) < 0.001) continue
      const x = beatToX(b)
      if (x < PIANO_KEY_WIDTH) continue
      ctx.beginPath()
      ctx.moveTo(Math.round(x) + 0.5, BAR_RULER_HEIGHT)
      ctx.lineTo(Math.round(x) + 0.5, H)
      ctx.stroke()
    }
  }

  // Beat lines
  for (let b = firstBeat; b <= lastBeat; b++) {
    const x = beatToX(b)
    if (x < PIANO_KEY_WIDTH) continue
    const isBar = b % bpb === 0
    ctx.strokeStyle = isBar ? c.gridBar : c.gridBeat
    ctx.lineWidth = isBar ? 1.5 : 1
    ctx.beginPath()
    ctx.moveTo(Math.round(x) + 0.5, BAR_RULER_HEIGHT)
    ctx.lineTo(Math.round(x) + 0.5, H)
    ctx.stroke()
  }

  // Horizontal pitch dividers (subtle line at bottom of each row)
  ctx.strokeStyle = 'rgba(255,255,255,0.03)'
  ctx.lineWidth = 1
  for (let pitch = MAX_PITCH; pitch >= MIN_PITCH; pitch--) {
    const y = pitchToY(pitch) + rh
    if (y < BAR_RULER_HEIGHT || y > H) continue
    ctx.beginPath()
    ctx.moveTo(PIANO_KEY_WIDTH, Math.round(y) + 0.5)
    ctx.lineTo(W, Math.round(y) + 0.5)
    ctx.stroke()
  }

  // 6. Ghost notes (non-active tracks at 30% opacity)
  for (let ti = 0; ti < props.tracks.length; ti++) {
    if (ti === props.activeTrackIndex) continue
    const track = props.tracks[ti]
    if (track.muted || !track.visible) continue
    ctx.globalAlpha = 0.3
    ctx.fillStyle = track.color
    for (const note of track.notes) {
      const nx = beatToX(note.start)
      const ny = pitchToY(note.pitch)
      const nw = note.duration * zoomX.value
      if (nx + nw < PIANO_KEY_WIDTH || nx > W || ny + rh < BAR_RULER_HEIGHT || ny > H) continue
      const clampX = Math.max(PIANO_KEY_WIDTH, nx)
      const drawW = Math.max(1, nw - (clampX - nx))
      fillRoundRect(ctx, clampX, ny + 1, drawW, rh - 2, NOTE_RADIUS)
    }
    ctx.globalAlpha = 1
  }

  // 7. Active track notes (skip if hidden)
  const aTrack = activeTrack.value
  if (aTrack && aTrack.visible) {
    const color = aTrack.color
    for (const note of aTrack.notes) {
      let nx = beatToX(note.start)
      let ny = pitchToY(note.pitch)
      let nw = note.duration * zoomX.value

      // Apply drag preview offset for move/resize
      if (dragState.value && dragState.value.originalNotes) {
        const orig = dragState.value.originalNotes.find((o) => o.id === note.id)
        if (orig) {
          if (dragState.value.type === 'move') {
            const deltaBeatPx = dragState.value.currentX - dragState.value.startX
            const deltaPitchPx = dragState.value.currentY - dragState.value.startY
            const deltaBeat = deltaBeatPx / zoomX.value
            const deltaPitch = -Math.round(deltaPitchPx / rh)
            const previewStart = snapBeat(orig.start + deltaBeat)
            const previewPitch = Math.max(MIN_PITCH, Math.min(MAX_PITCH, orig.pitch + deltaPitch))
            nx = beatToX(previewStart)
            ny = pitchToY(previewPitch)
          } else if (dragState.value.type === 'resize') {
            const deltaBeatPx = dragState.value.currentX - dragState.value.startX
            const deltaBeat = deltaBeatPx / zoomX.value
            const previewDuration = Math.max(
              props.gridSize,
              snapBeat(orig.duration + deltaBeat),
            )
            nw = previewDuration * zoomX.value
          }
        }
      }

      if (nx + nw < PIANO_KEY_WIDTH || nx > W || ny + rh < BAR_RULER_HEIGHT || ny > H) continue

      const clampX = Math.max(PIANO_KEY_WIDTH, nx)
      const drawW = Math.max(1, nw - (clampX - nx))

      // Fill
      ctx.fillStyle = color
      fillRoundRect(ctx, clampX, ny + 1, drawW, rh - 2, NOTE_RADIUS)

      // Velocity shading: darker overlay for lower velocity
      const velAlpha = 1 - note.velocity / 127
      if (velAlpha > 0.01) {
        ctx.fillStyle = `rgba(0,0,0,${velAlpha * 0.5})`
        fillRoundRect(ctx, clampX, ny + 1, drawW, rh - 2, NOTE_RADIUS)
      }

      // Selected border
      if (props.selectedNoteIds.has(note.id)) {
        ctx.strokeStyle = c.selectedBorder
        ctx.lineWidth = 2
        strokeRoundRect(ctx, clampX + 1, ny + 2, drawW - 2, rh - 4, NOTE_RADIUS)
      }
    }
  }

  // 8. Selection box
  if (dragState.value && dragState.value.type === 'select-box') {
    const ds = dragState.value
    const x1 = Math.min(ds.startX, ds.currentX)
    const y1 = Math.min(ds.startY, ds.currentY)
    const w = Math.abs(ds.currentX - ds.startX)
    const h = Math.abs(ds.currentY - ds.startY)
    ctx.fillStyle = c.selectionBox
    ctx.fillRect(x1, y1, w, h)
    ctx.strokeStyle = c.selectionBorder
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.strokeRect(x1, y1, w, h)
    ctx.setLineDash([])
  }

  // 8b. Draw preview (ghost note while dragging in draw mode)
  if (dragState.value && dragState.value.type === 'draw') {
    const ds = dragState.value
    const endBeat = xToBeat(ds.currentX)
    const snappedEnd = snapBeat(Math.max(0, endBeat))
    const duration = Math.max(props.gridSize, snappedEnd - ds.startBeat)
    const nx = beatToX(ds.startBeat)
    const ny = pitchToY(ds.startPitch)
    const nw = duration * zoomX.value
    const track = activeTrack.value
    const color = track?.color ?? '#4FC3F7'
    ctx.globalAlpha = 0.5
    ctx.fillStyle = color
    fillRoundRect(ctx, Math.max(PIANO_KEY_WIDTH, nx), ny + 1, nw, rh - 2, NOTE_RADIUS)
    ctx.globalAlpha = 1.0
  }

  // 4. Piano keys column (drawn after notes so it overlays them on the left edge)
  ctx.fillStyle = c.pianoColumnBg
  ctx.fillRect(0, 0, PIANO_KEY_WIDTH, H)

  for (let pitch = MAX_PITCH; pitch >= MIN_PITCH; pitch--) {
    const y = pitchToY(pitch)
    if (y + rh < 0 || y > H) continue

    const black = isBlackKey(pitch)
    ctx.fillStyle = black ? c.pianoBlack : c.pianoWhite
    ctx.fillRect(0, y, PIANO_KEY_WIDTH, rh)

    // Bottom border between keys
    ctx.strokeStyle = 'rgba(255,255,255,0.15)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, Math.round(y + rh) + 0.5)
    ctx.lineTo(PIANO_KEY_WIDTH, Math.round(y + rh) + 0.5)
    ctx.stroke()

    // Label C notes
    if (pitch % 12 === 0) {
      ctx.fillStyle = c.pianoLabel
      ctx.font = '10px monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(pitchName(pitch), PIANO_KEY_WIDTH / 2, y + rh / 2)
    }
  }

  // 5. Bar ruler (top strip)
  ctx.fillStyle = c.rulerBg
  ctx.fillRect(0, 0, W, BAR_RULER_HEIGHT)

  // Bar ruler bottom edge
  ctx.strokeStyle = 'rgba(255,255,255,0.2)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(0, BAR_RULER_HEIGHT + 0.5)
  ctx.lineTo(W, BAR_RULER_HEIGHT + 0.5)
  ctx.stroke()

  ctx.fillStyle = c.rulerText
  ctx.font = '11px monospace'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  for (let b = firstBeat; b <= lastBeat; b++) {
    if (b % bpb !== 0) continue
    const x = beatToX(b)
    if (x < PIANO_KEY_WIDTH - 10) continue
    const barNum = Math.floor(b / bpb) + 1
    ctx.fillText(String(barNum), Math.max(PIANO_KEY_WIDTH + 2, x + 3), BAR_RULER_HEIGHT / 2)

    // Tick mark
    ctx.strokeStyle = 'rgba(255,255,255,0.2)'
    ctx.beginPath()
    ctx.moveTo(Math.round(x) + 0.5, BAR_RULER_HEIGHT - 6)
    ctx.lineTo(Math.round(x) + 0.5, BAR_RULER_HEIGHT)
    ctx.stroke()
  }

  // Piano key / ruler corner overlap fill
  ctx.fillStyle = c.rulerBg
  ctx.fillRect(0, 0, PIANO_KEY_WIDTH, BAR_RULER_HEIGHT)

  // 9. Playback cursor
  const cursorX = beatToX(props.currentBeat)
  if (cursorX >= PIANO_KEY_WIDTH && cursorX <= W) {
    ctx.fillStyle = c.cursor
    ctx.fillRect(cursorX - 1, BAR_RULER_HEIGHT, 2, H - BAR_RULER_HEIGHT)

    // Small triangle at top
    ctx.beginPath()
    ctx.moveTo(cursorX - 5, BAR_RULER_HEIGHT)
    ctx.lineTo(cursorX + 5, BAR_RULER_HEIGHT)
    ctx.lineTo(cursorX, BAR_RULER_HEIGHT + 6)
    ctx.closePath()
    ctx.fill()
  }
}

// ── Animation loop ──

function renderLoop() {
  if (needsRedraw.value || props.isPlaying) {
    draw()
    needsRedraw.value = false
  }
  animFrameId = requestAnimationFrame(renderLoop)
}

function requestRedraw() {
  needsRedraw.value = true
}

// ── Canvas sizing ──

let resizeObserver: ResizeObserver | null = null
let _themeObserver: MutationObserver | null = null

function updateCanvasSize() {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !container) return

  const rect = container.getBoundingClientRect()
  const dpr = window.devicePixelRatio || 1
  const w = Math.round(rect.width)
  const h = Math.round(rect.height)

  // Skip if container hasn't been laid out yet
  if (w === 0 || h === 0) return

  // Only reset canvas buffer when dimensions actually changed (avoids
  // unnecessary context resets which clear the DPR transform).
  const bw = Math.round(w * dpr)
  const bh = Math.round(h * dpr)
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw
    canvas.height = bh
  }

  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`

  // Apply DPR transform — setting canvas.width/height resets all context state
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  requestRedraw()
}

// ── Mouse handling ──

function getCanvasPos(e: MouseEvent): { x: number; y: number } {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const rect = canvas.getBoundingClientRect()
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  }
}

function onMouseDown(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas) return
  canvas.focus()

  const { x, y } = getCanvasPos(e)

  // Piano key area — play note preview
  if (x < PIANO_KEY_WIDTH) {
    if (y > BAR_RULER_HEIGHT) {
      const pitch = yToPitch(y)
      if (pitch >= MIN_PITCH && pitch <= MAX_PITCH) {
        emit('play-note', pitch)
      }
    }
    return
  }

  // Ignore clicks in the ruler area
  if (y < BAR_RULER_HEIGHT) return

  const beat = xToBeat(x)
  const pitch = yToPitch(y)

  if (props.toolMode === 'select') {
    const hit = hitTestNote(x, y)
    if (hit) {
      // Select the note if not already selected (unless shift is held)
      if (!props.selectedNoteIds.has(hit.noteId)) {
        emit('select-notes', [hit.noteId], e.shiftKey)
      } else if (e.shiftKey) {
        // Shift-click on already selected note → toggle it off
        emit('select-notes', [hit.noteId], true)
        return
      }

      if (hit.edge === 'right') {
        // Start resize drag
        const ids = props.selectedNoteIds.has(hit.noteId)
          ? Array.from(props.selectedNoteIds)
          : [hit.noteId]
        const track = activeTrack.value
        if (!track) return
        const originals = ids
          .map((id) => {
            const n = track.notes.find((note) => note.id === id)
            if (!n) return null
            return { id: n.id, start: n.start, pitch: n.pitch, duration: n.duration }
          })
          .filter((o): o is NonNullable<typeof o> => o !== null)

        dragState.value = {
          type: 'resize',
          startX: x,
          startY: y,
          startBeat: beat,
          startPitch: pitch,
          currentX: x,
          currentY: y,
          noteId: hit.noteId,
          originalNotes: originals,
        }
      } else {
        // Start move drag
        const ids = props.selectedNoteIds.has(hit.noteId)
          ? Array.from(props.selectedNoteIds)
          : [hit.noteId]
        const track = activeTrack.value
        if (!track) return
        const originals = ids
          .map((id) => {
            const n = track.notes.find((note) => note.id === id)
            if (!n) return null
            return { id: n.id, start: n.start, pitch: n.pitch, duration: n.duration }
          })
          .filter((o): o is NonNullable<typeof o> => o !== null)

        dragState.value = {
          type: 'move',
          startX: x,
          startY: y,
          startBeat: beat,
          startPitch: pitch,
          currentX: x,
          currentY: y,
          noteId: hit.noteId,
          originalNotes: originals,
        }
      }
    } else {
      // Clicked empty space — start selection box
      if (!e.shiftKey) {
        emit('clear-selection')
      }
      dragState.value = {
        type: 'select-box',
        startX: x,
        startY: y,
        startBeat: beat,
        startPitch: pitch,
        currentX: x,
        currentY: y,
      }
    }
  } else if (props.toolMode === 'draw') {
    const snappedBeat = snapBeat(Math.max(0, beat))
    const clampedPitch = Math.max(MIN_PITCH, Math.min(MAX_PITCH, pitch))
    emit('play-note', clampedPitch)
    dragState.value = {
      type: 'draw',
      startX: x,
      startY: y,
      startBeat: snappedBeat,
      startPitch: clampedPitch,
      currentX: x,
      currentY: y,
    }
  }
}

function onMouseMove(e: MouseEvent) {
  const { x, y } = getCanvasPos(e)
  const canvas = canvasRef.value
  if (!canvas) return

  // Update cursor style
  if (props.toolMode === 'draw') {
    canvas.style.cursor = 'crosshair'
  } else if (props.toolMode === 'select') {
    if (dragState.value) {
      canvas.style.cursor =
        dragState.value.type === 'resize'
          ? 'ew-resize'
          : dragState.value.type === 'move'
            ? 'grabbing'
            : 'crosshair'
    } else if (x < PIANO_KEY_WIDTH) {
      canvas.style.cursor = 'pointer'
    } else {
      const hit = hitTestNote(x, y)
      if (hit) {
        canvas.style.cursor = hit.edge === 'right' ? 'ew-resize' : 'grab'
      } else {
        canvas.style.cursor = 'default'
      }
    }
  }

  // Handle drag state updates
  if (!dragState.value) return

  dragState.value.currentX = x
  dragState.value.currentY = y
  requestRedraw()
}

function onMouseUp(_e: MouseEvent) {
  if (!dragState.value) return

  const ds = dragState.value
  const rh = rowHeight.value

  if (ds.type === 'move' && ds.originalNotes) {
    const deltaBeatPx = ds.currentX - ds.startX
    const deltaPitchPx = ds.currentY - ds.startY
    const rawDeltaBeat = deltaBeatPx / zoomX.value
    const deltaBeat = snapBeat(ds.originalNotes[0].start + rawDeltaBeat) - ds.originalNotes[0].start
    const deltaPitch = -Math.round(deltaPitchPx / rh)

    // Only emit if there is a meaningful change
    if (Math.abs(deltaBeat) > 0.001 || deltaPitch !== 0) {
      const ids = ds.originalNotes.map((o) => o.id)
      emit('move-notes', ids, deltaBeat, deltaPitch)
    }
  } else if (ds.type === 'resize' && ds.originalNotes) {
    const deltaBeatPx = ds.currentX - ds.startX
    const deltaBeat = deltaBeatPx / zoomX.value
    // Use the first note's duration as reference
    const newDuration = Math.max(
      props.gridSize,
      snapBeat(ds.originalNotes[0].duration + deltaBeat),
    )
    const ids = ds.originalNotes.map((o) => o.id)
    emit('resize-notes', ids, newDuration)
  } else if (ds.type === 'select-box') {
    // Determine notes within the selection rectangle
    const beatA = xToBeat(ds.startX)
    const beatB = xToBeat(ds.currentX)
    const pitchA = yToPitch(ds.startY)
    const pitchB = yToPitch(ds.currentY)

    const minBeat = Math.min(beatA, beatB)
    const maxBeat = Math.max(beatA, beatB)
    const minPitch = Math.min(pitchA, pitchB)
    const maxPitch = Math.max(pitchA, pitchB)

    const track = activeTrack.value
    if (track) {
      const ids: string[] = []
      for (const note of track.notes) {
        const noteEnd = note.start + note.duration
        if (
          noteEnd > minBeat &&
          note.start < maxBeat &&
          note.pitch >= minPitch &&
          note.pitch <= maxPitch
        ) {
          ids.push(note.id)
        }
      }
      if (ids.length > 0) {
        emit('select-notes', ids, false)
      }
    }
  } else if (ds.type === 'draw') {
    const endBeat = xToBeat(ds.currentX)
    const snappedEnd = snapBeat(Math.max(0, endBeat))
    const duration = Math.max(props.gridSize, snappedEnd - ds.startBeat)
    emit('add-note', ds.startPitch, ds.startBeat, duration, 100)
  }

  dragState.value = null
  requestRedraw()
}

function onMouseLeave(_e: MouseEvent) {
  // If in a drag, treat as mouse up
  if (dragState.value) {
    onMouseUp(_e)
  }
}

// ── Wheel handling ──

function onWheel(e: WheelEvent) {
  e.preventDefault()

  if (e.ctrlKey || e.metaKey) {
    // Horizontal zoom centered on mouse
    const { x } = getCanvasPos(e)
    const beatUnderMouse = xToBeat(x)

    const zoomFactor = e.deltaY < 0 ? 1.15 : 1 / 1.15
    const newZoom = Math.max(10, Math.min(500, zoomX.value * zoomFactor))
    const oldZoom = zoomX.value
    zoomX.value = newZoom

    // Adjust scrollX so the beat under the mouse stays at the same pixel
    scrollX.value += beatUnderMouse * (newZoom - oldZoom)
    scrollX.value = Math.max(0, scrollX.value)
  } else if (e.shiftKey) {
    // Shift + wheel = horizontal scroll
    scrollX.value += e.deltaY
    scrollX.value = Math.max(0, scrollX.value)
  } else {
    // Wheel = vertical scroll (pitch)
    const containerH = containerRef.value?.getBoundingClientRect().height ?? 400
    const maxScrollY = Math.max(0, TOTAL_ROWS * rowHeight.value - containerH + BAR_RULER_HEIGHT)
    scrollY.value += e.deltaY
    scrollY.value = Math.max(0, Math.min(maxScrollY, scrollY.value))
  }

  requestRedraw()
}

// ── Keyboard handling ──

function onKeyDown(e: KeyboardEvent) {
  const ctrl = e.ctrlKey || e.metaKey
  if (ctrl && e.key === 'z') {
    e.preventDefault()
    e.stopPropagation()
    emit('undo')
  } else if (ctrl && (e.key === 'y' || (e.shiftKey && e.key === 'Z'))) {
    e.preventDefault()
    e.stopPropagation()
    emit('redo')
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    if (props.selectedNoteIds.size > 0) {
      e.preventDefault()
      e.stopPropagation()
      emit('delete-notes', Array.from(props.selectedNoteIds))
    }
  } else if (ctrl && e.key === 'a') {
    e.preventDefault()
    e.stopPropagation()
    emit('select-all')
  } else if (ctrl && e.key === 'c') {
    e.preventDefault()
    e.stopPropagation()
    emit('copy')
  } else if (ctrl && e.key === 'v') {
    e.preventDefault()
    e.stopPropagation()
    emit('paste', props.currentBeat)
  } else if (ctrl && e.key === 'd') {
    e.preventDefault()
    e.stopPropagation()
    emit('duplicate')
  } else if (e.key === 'Escape') {
    emit('clear-selection')
    dragState.value = null
    requestRedraw()
  }
}

// ── Auto-scroll to note range ──

let hasAutoScrolled = false

function autoScrollToNotes() {
  // Gather all pitches across all tracks
  let minPitch = MAX_PITCH
  let maxPitch = MIN_PITCH
  let hasNotes = false
  for (const track of props.tracks) {
    for (const note of track.notes) {
      if (note.pitch < minPitch) minPitch = note.pitch
      if (note.pitch > maxPitch) maxPitch = note.pitch
      hasNotes = true
    }
  }
  if (!hasNotes) return

  const container = containerRef.value
  if (!container) return
  const containerHeight = container.getBoundingClientRect().height
  if (containerHeight <= 0) return

  // Center viewport on the mid-point of the note range, with some padding
  const midPitch = Math.round((minPitch + maxPitch) / 2)
  const midRow = MAX_PITCH - midPitch
  scrollY.value = Math.max(0, midRow * rowHeight.value - containerHeight / 2 + BAR_RULER_HEIGHT)
  hasAutoScrolled = true
  requestRedraw()
}

// ── Watchers ──

watch(
  () => [
    props.tracks,
    props.selectedNoteIds,
    props.activeTrackIndex,
    props.gridSize,
    props.timeSignature,
    props.toolMode,
  ],
  () => {
    // Auto-scroll to note content on first data load
    if (!hasAutoScrolled && props.tracks.some((t) => t.notes.length > 0)) {
      autoScrollToNotes()
    }
    requestRedraw()
  },
  { deep: true },
)

watch(
  () => props.currentBeat,
  () => {
    // During playback, auto-scroll to keep cursor visible
    if (props.isPlaying) {
      const cursorX = beatToX(props.currentBeat)
      const canvas = canvasRef.value
      if (canvas) {
        const w = canvas.getBoundingClientRect().width
        if (cursorX > w - 100) {
          scrollX.value += w * 0.6
        } else if (cursorX < PIANO_KEY_WIDTH + 50) {
          scrollX.value = Math.max(0, props.currentBeat * zoomX.value - 100)
        }
      }
    }
    requestRedraw()
  },
)

watch([scrollX, scrollY, zoomX, zoomY], () => {
  requestRedraw()
})

// ── Lifecycle ──

onMounted(async () => {
  await nextTick()
  updateCanvasSize()

  // If tracks already have notes, center on the actual note range;
  // otherwise default to centering around C4 (pitch 60).
  if (props.tracks.some((t) => t.notes.length > 0)) {
    autoScrollToNotes()
  } else {
    const c4Row = MAX_PITCH - 60
    const container = containerRef.value
    if (container) {
      const containerHeight = container.getBoundingClientRect().height
      scrollY.value = Math.max(0, c4Row * rowHeight.value - containerHeight / 2)
    }
  }

  // Start render loop
  animFrameId = requestAnimationFrame(renderLoop)

  // Redraw on theme change
  _themeObserver = new MutationObserver(() => requestRedraw())
  _themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })

  // Observe container resizing
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      updateCanvasSize()
    })
    resizeObserver.observe(containerRef.value)
  }

  // Attach event listeners
  const canvas = canvasRef.value
  if (canvas) {
    canvas.addEventListener('mousedown', onMouseDown)
    canvas.addEventListener('mousemove', onMouseMove)
    canvas.addEventListener('mouseup', onMouseUp)
    canvas.addEventListener('mouseleave', onMouseLeave)
    canvas.addEventListener('wheel', onWheel, { passive: false })
    canvas.addEventListener('keydown', onKeyDown)
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animFrameId)

  _themeObserver?.disconnect()

  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }

  const canvas = canvasRef.value
  if (canvas) {
    canvas.removeEventListener('mousedown', onMouseDown)
    canvas.removeEventListener('mousemove', onMouseMove)
    canvas.removeEventListener('mouseup', onMouseUp)
    canvas.removeEventListener('mouseleave', onMouseLeave)
    canvas.removeEventListener('wheel', onWheel)
    canvas.removeEventListener('keydown', onKeyDown)
  }
})

// ── Expose for external sync (e.g., VelocityEditor) ──

defineExpose({ scrollX, zoomX, canvasRef })
</script>

<template>
  <div class="midi-piano-roll" ref="containerRef">
    <canvas ref="canvasRef" tabindex="0" />
  </div>
</template>

<style lang="scss">
.midi-piano-roll {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;

  canvas {
    display: block;
    width: 100%;
    height: 100%;
    outline: none;
  }
}
</style>
