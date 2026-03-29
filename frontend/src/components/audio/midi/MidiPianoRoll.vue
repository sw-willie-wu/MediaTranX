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
}>()

// ── Constants ──

const PIANO_KEY_WIDTH = 48
const BAR_RULER_HEIGHT = 24
const NOTE_HEIGHT = 14
const MIN_PITCH = 21   // A0
const MAX_PITCH = 108  // C8
const TOTAL_ROWS = MAX_PITCH - MIN_PITCH + 1

const RESIZE_HANDLE_PX = 6 // pixels from right edge to trigger resize

// Colors (canvas can't read CSS vars — define here)
const COLOR_DARK_ROW = '#1a1a2e'
const COLOR_LIGHT_ROW = '#1e1e35'
const COLOR_GRID_BEAT = 'rgba(255,255,255,0.06)'
const COLOR_GRID_BAR = 'rgba(255,255,255,0.15)'
const COLOR_GRID_SUB = 'rgba(255,255,255,0.03)'
const COLOR_PIANO_WHITE = '#2a2a44'
const COLOR_PIANO_BLACK = '#16162a'
const COLOR_PIANO_LABEL = '#aaaacc'
const COLOR_RULER_BG = '#12122a'
const COLOR_RULER_TEXT = '#8888aa'
const COLOR_CURSOR = '#ff4444'
const COLOR_SELECTION_BOX = 'rgba(100,160,255,0.25)'
const COLOR_SELECTION_BORDER = 'rgba(100,160,255,0.7)'
const COLOR_SELECTED_BORDER = '#ffffff'

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
  type: 'none' | 'move' | 'resize' | 'select-box' | 'scroll'
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

  const W = canvas.width
  const H = canvas.height
  const rh = rowHeight.value
  const bpb = beatsPerBar.value

  // 1. Clear
  ctx.clearRect(0, 0, W, H)

  // 2. Background rows
  for (let pitch = MAX_PITCH; pitch >= MIN_PITCH; pitch--) {
    const y = pitchToY(pitch)
    if (y + rh < BAR_RULER_HEIGHT || y > H) continue
    ctx.fillStyle = isBlackKey(pitch) ? COLOR_DARK_ROW : COLOR_LIGHT_ROW
    ctx.fillRect(PIANO_KEY_WIDTH, y, W - PIANO_KEY_WIDTH, rh)
  }

  // 3. Grid lines
  const firstBeat = Math.max(0, Math.floor(xToBeat(PIANO_KEY_WIDTH)))
  const lastBeat = Math.ceil(xToBeat(W))

  // Sub-beat grid lines (gridSize)
  if (props.gridSize < 1) {
    const gs = props.gridSize
    const firstSub = Math.max(0, Math.floor(xToBeat(PIANO_KEY_WIDTH) / gs) * gs)
    ctx.strokeStyle = COLOR_GRID_SUB
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
    ctx.strokeStyle = isBar ? COLOR_GRID_BAR : COLOR_GRID_BEAT
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
    if (track.muted) continue
    ctx.globalAlpha = 0.3
    ctx.fillStyle = track.color
    for (const note of track.notes) {
      const nx = beatToX(note.start)
      const ny = pitchToY(note.pitch)
      const nw = note.duration * zoomX.value
      if (nx + nw < PIANO_KEY_WIDTH || nx > W || ny + rh < BAR_RULER_HEIGHT || ny > H) continue
      const clampX = Math.max(PIANO_KEY_WIDTH, nx)
      const drawW = Math.max(1, nw - (clampX - nx))
      ctx.fillRect(clampX, ny + 1, drawW, rh - 2)
    }
    ctx.globalAlpha = 1
  }

  // 7. Active track notes
  const aTrack = activeTrack.value
  if (aTrack) {
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
      ctx.fillRect(clampX, ny + 1, drawW, rh - 2)

      // Velocity shading: darker overlay for lower velocity
      const velAlpha = 1 - note.velocity / 127
      if (velAlpha > 0.01) {
        ctx.fillStyle = `rgba(0,0,0,${velAlpha * 0.5})`
        ctx.fillRect(clampX, ny + 1, drawW, rh - 2)
      }

      // Selected border
      if (props.selectedNoteIds.has(note.id)) {
        ctx.strokeStyle = COLOR_SELECTED_BORDER
        ctx.lineWidth = 2
        ctx.strokeRect(clampX + 1, ny + 2, drawW - 2, rh - 4)
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
    ctx.fillStyle = COLOR_SELECTION_BOX
    ctx.fillRect(x1, y1, w, h)
    ctx.strokeStyle = COLOR_SELECTION_BORDER
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.strokeRect(x1, y1, w, h)
    ctx.setLineDash([])
  }

  // 4. Piano keys column (drawn after notes so it overlays them on the left edge)
  ctx.fillStyle = COLOR_RULER_BG
  ctx.fillRect(0, 0, PIANO_KEY_WIDTH, H)

  for (let pitch = MAX_PITCH; pitch >= MIN_PITCH; pitch--) {
    const y = pitchToY(pitch)
    if (y + rh < 0 || y > H) continue

    const black = isBlackKey(pitch)
    ctx.fillStyle = black ? COLOR_PIANO_BLACK : COLOR_PIANO_WHITE
    ctx.fillRect(0, y, PIANO_KEY_WIDTH, rh)

    // Subtle bottom border
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, Math.round(y + rh) + 0.5)
    ctx.lineTo(PIANO_KEY_WIDTH, Math.round(y + rh) + 0.5)
    ctx.stroke()

    // Label C notes
    if (pitch % 12 === 0) {
      ctx.fillStyle = COLOR_PIANO_LABEL
      ctx.font = '10px monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(pitchName(pitch), PIANO_KEY_WIDTH / 2, y + rh / 2)
    }
  }

  // 5. Bar ruler (top strip)
  ctx.fillStyle = COLOR_RULER_BG
  ctx.fillRect(0, 0, W, BAR_RULER_HEIGHT)

  // Bar ruler bottom edge
  ctx.strokeStyle = 'rgba(255,255,255,0.1)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(0, BAR_RULER_HEIGHT + 0.5)
  ctx.lineTo(W, BAR_RULER_HEIGHT + 0.5)
  ctx.stroke()

  ctx.fillStyle = COLOR_RULER_TEXT
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
  ctx.fillStyle = COLOR_RULER_BG
  ctx.fillRect(0, 0, PIANO_KEY_WIDTH, BAR_RULER_HEIGHT)

  // 9. Playback cursor
  const cursorX = beatToX(props.currentBeat)
  if (cursorX >= PIANO_KEY_WIDTH && cursorX <= W) {
    ctx.fillStyle = COLOR_CURSOR
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

function updateCanvasSize() {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !container) return

  const rect = container.getBoundingClientRect()
  const dpr = window.devicePixelRatio || 1
  const w = Math.round(rect.width)
  const h = Math.round(rect.height)

  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`

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
    // Create a new note
    const snappedBeat = snapBeat(Math.max(0, beat))
    const clampedPitch = Math.max(MIN_PITCH, Math.min(MAX_PITCH, pitch))
    emit('add-note', clampedPitch, snappedBeat, props.gridSize, 100)
  } else if (props.toolMode === 'erase') {
    const hit = hitTestNote(x, y)
    if (hit) {
      emit('delete-notes', [hit.noteId])
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
  } else if (props.toolMode === 'erase') {
    canvas.style.cursor = x < PIANO_KEY_WIDTH ? 'default' : 'not-allowed'
    // If hovering over a note in erase mode, show pointer
    if (x >= PIANO_KEY_WIDTH && hitTestNote(x, y)) {
      canvas.style.cursor = 'pointer'
    }
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
    // Vertical scroll
    scrollY.value += e.deltaY
    scrollY.value = Math.max(0, Math.min(TOTAL_ROWS * rowHeight.value - 200, scrollY.value))
  } else {
    // Horizontal scroll
    scrollX.value += e.deltaY
    scrollX.value = Math.max(0, scrollX.value)
  }

  requestRedraw()
}

// ── Keyboard handling ──

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (props.selectedNoteIds.size > 0) {
      e.preventDefault()
      emit('delete-notes', Array.from(props.selectedNoteIds))
    }
  } else if (e.key === 'Escape') {
    emit('clear-selection')
    dragState.value = null
    requestRedraw()
  }
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

  // Set initial scroll to center around C4 (pitch 60)
  const c4Row = MAX_PITCH - 60
  const container = containerRef.value
  if (container) {
    const containerHeight = container.getBoundingClientRect().height
    scrollY.value = Math.max(0, c4Row * rowHeight.value - containerHeight / 2)
  }

  // Start render loop
  animFrameId = requestAnimationFrame(renderLoop)

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
