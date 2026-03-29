/**
 * MIDI Editor 核心狀態管理 composable
 */
import { ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { apiFetch } from '@/composables/useApi'

// ── Types ──

export interface MidiNote {
  id: string
  pitch: number      // 0-127
  start: number      // in beats
  duration: number   // in beats
  velocity: number   // 0-127
}

export interface MidiTrack {
  name: string
  instrument: number   // GM program 0-127
  color: string
  volume: number       // 0-127
  pan: number          // 0-127 (64=center)
  muted: boolean
  isDrum: boolean
  notes: MidiNote[]
}

export interface MidiData {
  ticksPerBeat: number
  tempo: number
  timeSignature: [number, number]
  tracks: MidiTrack[]
}

export type ToolMode = 'select' | 'draw' | 'erase'

// ── Constants ──

const TRACK_COLORS = [
  '#4FC3F7', '#81C784', '#FFB74D', '#E57373',
  '#BA68C8', '#4DD0E1', '#AED581', '#FF8A65',
  '#9575CD', '#4DB6AC', '#DCE775', '#F06292',
]

const MAX_UNDO = 100

// ── Composable ──

export function useMidiEditor() {
  // ── State refs ──
  const tracks: Ref<MidiTrack[]> = ref([])
  const activeTrackIndex: Ref<number> = ref(0)
  const selectedNoteIds: Ref<Set<string>> = ref(new Set())
  const clipboard: Ref<MidiNote[]> = ref([])
  const toolMode: Ref<ToolMode> = ref('select')
  const tempo: Ref<number> = ref(120)
  const timeSignature: Ref<[number, number]> = ref([4, 4])
  const ticksPerBeat: Ref<number> = ref(480)
  const gridSize: Ref<number> = ref(0.25)
  const snapEnabled: Ref<boolean> = ref(true)
  const isDirty: Ref<boolean> = ref(false)
  const isLoading: Ref<boolean> = ref(false)

  // ── Computed ──
  const activeTrack: ComputedRef<MidiTrack | null> = computed(() => {
    const idx = activeTrackIndex.value
    if (idx >= 0 && idx < tracks.value.length) {
      return tracks.value[idx]
    }
    return null
  })

  // ── Undo / Redo ──
  const undoStack: MidiData[] = []
  const redoStack: MidiData[] = []

  const canUndo: ComputedRef<boolean> = computed(() => undoStack.length > 0)
  const canRedo: ComputedRef<boolean> = computed(() => redoStack.length > 0)

  function snapshotState(): MidiData {
    return {
      ticksPerBeat: ticksPerBeat.value,
      tempo: tempo.value,
      timeSignature: [...timeSignature.value] as [number, number],
      tracks: tracks.value.map((t) => ({
        ...t,
        notes: t.notes.map((n) => ({ ...n })),
      })),
    }
  }

  function restoreState(snapshot: MidiData) {
    ticksPerBeat.value = snapshot.ticksPerBeat
    tempo.value = snapshot.tempo
    timeSignature.value = [...snapshot.timeSignature] as [number, number]
    tracks.value = snapshot.tracks.map((t) => ({
      ...t,
      notes: t.notes.map((n) => ({ ...n })),
    }))
    // Clamp activeTrackIndex to valid range
    if (activeTrackIndex.value >= tracks.value.length) {
      activeTrackIndex.value = Math.max(0, tracks.value.length - 1)
    }
    selectedNoteIds.value = new Set()
  }

  function pushUndo() {
    undoStack.push(snapshotState())
    if (undoStack.length > MAX_UNDO) {
      undoStack.shift()
    }
    redoStack.length = 0
    isDirty.value = true
  }

  function undo() {
    if (undoStack.length === 0) return
    redoStack.push(snapshotState())
    const snapshot = undoStack.pop()!
    restoreState(snapshot)
  }

  function redo() {
    if (redoStack.length === 0) return
    undoStack.push(snapshotState())
    const snapshot = redoStack.pop()!
    restoreState(snapshot)
  }

  // ── API methods ──

  async function loadFromApi(fileId: string) {
    isLoading.value = true
    try {
      const res = await apiFetch(`/audio/midi/${fileId}`)
      if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`)
      }
      const json = await res.json()

      // Convert snake_case API response to camelCase state
      ticksPerBeat.value = json.ticks_per_beat ?? json.ticksPerBeat ?? 480
      tempo.value = json.tempo ?? 120
      timeSignature.value = json.time_signature ?? json.timeSignature ?? [4, 4]

      tracks.value = (json.tracks ?? []).map((apiTrack: any, idx: number) => ({
        name: apiTrack.name ?? `Track ${idx + 1}`,
        instrument: apiTrack.instrument ?? 0,
        color: apiTrack.color ?? TRACK_COLORS[idx % TRACK_COLORS.length],
        volume: apiTrack.volume ?? 100,
        pan: apiTrack.pan ?? 64,
        muted: apiTrack.muted ?? false,
        isDrum: apiTrack.is_drum ?? apiTrack.isDrum ?? false,
        notes: (apiTrack.notes ?? []).map((apiNote: any) => ({
          id: crypto.randomUUID(),
          pitch: apiNote.pitch ?? 60,
          start: apiNote.start ?? 0,
          duration: apiNote.duration ?? 1,
          velocity: apiNote.velocity ?? 100,
        })),
      }))

      activeTrackIndex.value = 0
      selectedNoteIds.value = new Set()
      clipboard.value = []
      isDirty.value = false
      undoStack.length = 0
      redoStack.length = 0
    } finally {
      isLoading.value = false
    }
  }

  async function saveToApi(fileId: string) {
    isLoading.value = true
    try {
      const payload = {
        data: {
          ticks_per_beat: ticksPerBeat.value,
          tempo: tempo.value,
          time_signature: [...timeSignature.value],
          tracks: tracks.value.map((t) => ({
            name: t.name,
            instrument: t.instrument,
            color: t.color,
            volume: t.volume,
            pan: t.pan,
            muted: t.muted,
            is_drum: t.isDrum,
            notes: t.notes.map((n) => ({
              pitch: n.pitch,
              start: n.start,
              duration: n.duration,
              velocity: n.velocity,
            })),
          })),
        },
      }

      const res = await apiFetch(`/audio/midi/${fileId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`)
      }

      isDirty.value = false
    } finally {
      isLoading.value = false
    }
  }

  // ── Note operations ──

  function addNote(
    pitch: number,
    start: number,
    duration: number = 1,
    velocity: number = 100,
  ): string | null {
    const track = activeTrack.value
    if (!track) return null

    pushUndo()

    const id = crypto.randomUUID()
    track.notes.push({
      id,
      pitch: clampPitch(pitch),
      start,
      duration,
      velocity: clampVelocity(velocity),
    })

    return id
  }

  function deleteNotes(ids: string[]) {
    const track = activeTrack.value
    if (!track || ids.length === 0) return

    pushUndo()

    const idSet = new Set(ids)
    track.notes = track.notes.filter((n) => !idSet.has(n.id))
    // Remove deleted notes from selection
    for (const id of ids) {
      selectedNoteIds.value.delete(id)
    }
  }

  function moveNotes(ids: string[], deltaBeat: number, deltaPitch: number) {
    const track = activeTrack.value
    if (!track || ids.length === 0) return

    pushUndo()

    const idSet = new Set(ids)
    for (const note of track.notes) {
      if (idSet.has(note.id)) {
        note.start = Math.max(0, note.start + deltaBeat)
        note.pitch = clampPitch(note.pitch + deltaPitch)
      }
    }
  }

  function resizeNotes(ids: string[], newDuration: number) {
    const track = activeTrack.value
    if (!track || ids.length === 0) return

    pushUndo()

    const safeDuration = Math.max(0.0625, newDuration) // minimum 1/64 beat
    const idSet = new Set(ids)
    for (const note of track.notes) {
      if (idSet.has(note.id)) {
        note.duration = safeDuration
      }
    }
  }

  function updateVelocity(ids: string[], velocity: number) {
    const track = activeTrack.value
    if (!track || ids.length === 0) return

    pushUndo()

    const safeVelocity = clampVelocity(velocity)
    const idSet = new Set(ids)
    for (const note of track.notes) {
      if (idSet.has(note.id)) {
        note.velocity = safeVelocity
      }
    }
  }

  // ── Selection ──

  function selectNote(id: string, addToSelection: boolean = false) {
    if (addToSelection) {
      if (selectedNoteIds.value.has(id)) {
        selectedNoteIds.value.delete(id)
      } else {
        selectedNoteIds.value.add(id)
      }
      // Trigger reactivity
      selectedNoteIds.value = new Set(selectedNoteIds.value)
    } else {
      selectedNoteIds.value = new Set([id])
    }
  }

  function selectNotesInRange(
    startBeat: number,
    endBeat: number,
    startPitch: number,
    endPitch: number,
  ) {
    const track = activeTrack.value
    if (!track) return

    const minBeat = Math.min(startBeat, endBeat)
    const maxBeat = Math.max(startBeat, endBeat)
    const minPitch = Math.min(startPitch, endPitch)
    const maxPitch = Math.max(startPitch, endPitch)

    const ids = new Set<string>()
    for (const note of track.notes) {
      const noteEnd = note.start + note.duration
      if (
        noteEnd > minBeat &&
        note.start < maxBeat &&
        note.pitch >= minPitch &&
        note.pitch <= maxPitch
      ) {
        ids.add(note.id)
      }
    }
    selectedNoteIds.value = ids
  }

  function selectAll() {
    const track = activeTrack.value
    if (!track) return
    selectedNoteIds.value = new Set(track.notes.map((n) => n.id))
  }

  function clearSelection() {
    selectedNoteIds.value = new Set()
  }

  // ── Clipboard ──

  function copySelection() {
    const track = activeTrack.value
    if (!track) return

    const selected = track.notes.filter((n) => selectedNoteIds.value.has(n.id))
    clipboard.value = selected.map((n) => ({ ...n }))
  }

  function pasteAtBeat(beat: number) {
    const track = activeTrack.value
    if (!track || clipboard.value.length === 0) return

    pushUndo()

    // Find the earliest start in clipboard to compute offset
    const minStart = Math.min(...clipboard.value.map((n) => n.start))
    const offset = beat - minStart

    const newIds: string[] = []
    for (const note of clipboard.value) {
      const id = crypto.randomUUID()
      track.notes.push({
        id,
        pitch: note.pitch,
        start: note.start + offset,
        duration: note.duration,
        velocity: note.velocity,
      })
      newIds.push(id)
    }

    // Select pasted notes
    selectedNoteIds.value = new Set(newIds)
  }

  function duplicateSelection() {
    const track = activeTrack.value
    if (!track) return

    const selected = track.notes.filter((n) => selectedNoteIds.value.has(n.id))
    if (selected.length === 0) return

    // Copy selected notes
    copySelection()

    // Find the end of the selection (max of start + duration)
    const endBeat = Math.max(...selected.map((n) => n.start + n.duration))
    pasteAtBeat(endBeat)
  }

  // ── Track operations ──

  function addTrack(
    name?: string,
    instrument: number = 0,
    isDrum: boolean = false,
  ) {
    pushUndo()

    const idx = tracks.value.length
    const color = TRACK_COLORS[idx % TRACK_COLORS.length]
    tracks.value.push({
      name: name ?? `Track ${idx + 1}`,
      instrument,
      color,
      volume: 100,
      pan: 64,
      muted: false,
      isDrum,
      notes: [],
    })

    activeTrackIndex.value = idx
  }

  function deleteTrack(index: number) {
    if (index < 0 || index >= tracks.value.length) return

    pushUndo()

    tracks.value.splice(index, 1)

    // Adjust activeTrackIndex
    if (tracks.value.length === 0) {
      activeTrackIndex.value = 0
    } else if (activeTrackIndex.value >= tracks.value.length) {
      activeTrackIndex.value = tracks.value.length - 1
    } else if (activeTrackIndex.value > index) {
      activeTrackIndex.value--
    }

    selectedNoteIds.value = new Set()
  }

  function updateTrack(index: number, patch: Partial<MidiTrack>) {
    if (index < 0 || index >= tracks.value.length) return

    pushUndo()

    const track = tracks.value[index]
    Object.assign(track, patch)
  }

  // ── Tools ──

  function quantize(resolution: number) {
    const track = activeTrack.value
    if (!track || selectedNoteIds.value.size === 0) return

    pushUndo()

    for (const note of track.notes) {
      if (selectedNoteIds.value.has(note.id)) {
        note.start = Math.round(note.start / resolution) * resolution
      }
    }
  }

  function transpose(semitones: number) {
    const track = activeTrack.value
    if (!track || selectedNoteIds.value.size === 0) return

    pushUndo()

    for (const note of track.notes) {
      if (selectedNoteIds.value.has(note.id)) {
        note.pitch = clampPitch(note.pitch + semitones)
      }
    }
  }

  // ── Helpers ──

  function snapToGrid(beat: number): number {
    if (!snapEnabled.value) return beat
    return Math.round(beat / gridSize.value) * gridSize.value
  }

  function getTotalBeats(): number {
    let max = 0
    for (const track of tracks.value) {
      for (const note of track.notes) {
        const end = note.start + note.duration
        if (end > max) max = end
      }
    }
    return max
  }

  function clampPitch(pitch: number): number {
    return Math.max(0, Math.min(127, Math.round(pitch)))
  }

  function clampVelocity(velocity: number): number {
    return Math.max(0, Math.min(127, Math.round(velocity)))
  }

  // ── Return ──

  return {
    // State
    tracks,
    activeTrackIndex,
    activeTrack,
    selectedNoteIds,
    clipboard,
    toolMode,
    tempo,
    timeSignature,
    ticksPerBeat,
    gridSize,
    snapEnabled,
    isDirty,
    isLoading,

    // Undo / Redo
    canUndo,
    canRedo,
    pushUndo,
    undo,
    redo,

    // API
    loadFromApi,
    saveToApi,

    // Note operations
    addNote,
    deleteNotes,
    moveNotes,
    resizeNotes,
    updateVelocity,

    // Selection
    selectNote,
    selectNotesInRange,
    selectAll,
    clearSelection,

    // Clipboard
    copySelection,
    pasteAtBeat,
    duplicateSelection,

    // Track operations
    addTrack,
    deleteTrack,
    updateTrack,

    // Tools
    quantize,
    transpose,

    // Helpers
    snapToGrid,
    getTotalBeats,
  }
}
