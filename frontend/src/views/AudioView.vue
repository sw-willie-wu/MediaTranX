<script setup lang="ts">
import { ref, computed, watch, watchEffect, nextTick, defineAsyncComponent, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { useI18n } from 'vue-i18n'
import ToolLayout from '@/components/ToolLayout.vue'
import AppFilmstrip from '@/components/common/AppFilmstrip.vue'
import AudioPreview from '@/components/audio/AudioPreview.vue'
import AudioMultiTrackPreview from '@/components/audio/AudioMultiTrackPreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import AudioTranscodePanel  from '@/components/audio/panels/AudioTranscodePanel.vue'
import AudioCutPanel        from '@/components/audio/panels/AudioCutPanel.vue'
import AudioVolumePanel     from '@/components/audio/panels/AudioVolumePanel.vue'
import AudioTranscribePanel from '@/components/audio/panels/AudioTranscribePanel.vue'
import AudioSeparatePanel  from '@/components/audio/panels/AudioSeparatePanel.vue'
import AudioLyricsPanel    from '@/components/audio/panels/AudioLyricsPanel.vue'
const AudioMidiEditPanel = defineAsyncComponent(
  () => import('@/components/audio/panels/AudioMidiEditPanel.vue')
)
const MidiPianoRoll = defineAsyncComponent(() => import('@/components/audio/midi/MidiPianoRoll.vue'))
const MidiVelocityEditor = defineAsyncComponent(() => import('@/components/audio/midi/MidiVelocityEditor.vue'))
import MidiToolbar from '@/components/audio/midi/MidiToolbar.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import TextPreviewModal from '@/components/common/TextPreviewModal.vue'
import { GM_INSTRUMENT_OPTIONS } from '@/constants/midiInstruments'
import { useAudioWorkspace } from '@/composables/useAudioWorkspace'
import { useToast } from '@/composables/useToast'
import { useMidiPlayback } from '@/composables/useMidiPlayback'
import { useMultiSubmit } from '@/composables/useMultiSubmit'
import { useTaskStore } from '@/stores/tasks'
import { useTitlebar, type TitlebarExtraAction } from '@/composables/useTitlebar'
import { apiFetch } from '@/composables/useApi'

const { t } = useI18n()
const toast = useToast()

const {
  hasFile, fileId, activeFileId, activePreviewUrl, isUploading, sourceDir, currentFileName, hasResult, audioInfo,
  canGoBack, canGoForward,
  textResultContent, textResultFileId,
  collection,
  handleFile, handleFiles, handleRemoveFile, handlePanelSubmit, handleDownload, downloadFile, addMidiEntry,
  goBack, goForward,
} = useAudioWorkspace()

const selectedIds = computed(() => collection.selectedIds.value)
const isMultiSelect = computed(() => selectedIds.value.size > 1)
const { isSubmitting, submitToAll } = useMultiSubmit(collection)

// Panel refs
const transcodePanelRef  = ref<InstanceType<typeof AudioTranscodePanel>  | null>(null)
const cutPanelRef        = ref<InstanceType<typeof AudioCutPanel>        | null>(null)
const volumePanelRef     = ref<InstanceType<typeof AudioVolumePanel>     | null>(null)
const transcribePanelRef = ref<InstanceType<typeof AudioTranscribePanel> | null>(null)
const separatePanelRef   = ref<InstanceType<typeof AudioSeparatePanel>  | null>(null)
const lyricsPanelRef     = ref<InstanceType<typeof AudioLyricsPanel>    | null>(null)
const midiEditPanelRef   = ref<InstanceType<typeof AudioMidiEditPanel>  | null>(null)
const pianoRollRef       = ref<InstanceType<typeof MidiPianoRoll>       | null>(null)

// ── MIDI Playback ──
const midiPlayback = useMidiPlayback()

// Sync playback with editor state
watch(() => midiEditPanelRef.value?.editor?.tracks.value, (t) => {
  if (t) midiPlayback.setTracks(t)
}, { deep: true })

watch(() => midiEditPanelRef.value?.editor?.tempo.value, (bpm) => {
  if (bpm) midiPlayback.setTempo(bpm)
})

// ── MIDI track bar state ──
const expandedTrackIdx = ref<number | null>(null)

function toggleTrackSettings(idx: number) {
  expandedTrackIdx.value = expandedTrackIdx.value === idx ? null : idx
}

function toggleSolo(idx: number) {
  if (!midiEditPanelRef.value?.editor) return
  const tracks = midiEditPanelRef.value.editor.tracks.value
  const wasSolo = tracks[idx].solo
  // 關掉所有 solo，再 toggle 目標軌
  for (const t of tracks) t.solo = false
  if (!wasSolo) tracks[idx].solo = true
}

function removeTrack(idx: number) {
  if (!midiEditPanelRef.value?.editor) return
  const ed = midiEditPanelRef.value.editor
  if (ed.tracks.value.length <= 1) return
  // Close settings drawer if it's the one being removed
  if (expandedTrackIdx.value === idx) expandedTrackIdx.value = null
  else if (expandedTrackIdx.value !== null && expandedTrackIdx.value > idx) expandedTrackIdx.value--
  ed.deleteTrack(idx)
}

function addTrack() {
  if (!midiEditPanelRef.value?.editor) return
  midiEditPanelRef.value.editor.addTrack()
}

function onTrackBarWheel(e: WheelEvent) {
  const el = e.currentTarget as HTMLElement
  el.scrollLeft += e.deltaY || e.deltaX
}

// ── MIDI instrument options (with Drum Kit at top) ──
const instrumentOptionsWithDrum = computed(() => [
  { value: -1, label: 'Drum Kit' },
  ...GM_INSTRUMENT_OPTIONS,
])

function onInstrumentChange(trackIdx: number, value: number) {
  if (value === -1) {
    midiEditPanelRef.value?.editor.updateTrack(trackIdx, { isDrum: true })
  } else {
    midiEditPanelRef.value?.editor.updateTrack(trackIdx, { instrument: value, isDrum: false })
  }
}

// ── MIDI file detection ──
const isMidiFile = computed(() => {
  const name = currentFileName.value?.toLowerCase() || ''
  return name.endsWith('.mid') || name.endsWith('.midi')
})

const subFunctions = computed(() => [
  { id: 'transcode',  name: t('audio.functions.transcode'),  icon: 'bi-arrow-repeat',     group: t('audio.group.edit') },
  { id: 'cut',        name: t('audio.functions.cut'),        icon: 'bi-scissors',         group: t('audio.group.edit') },
  { id: 'volume',     name: t('audio.functions.volume'),     icon: 'bi-volume-up-fill',   group: t('audio.group.edit') },
  { id: 'midi-edit',  name: t('audio.functions.midiEdit'),   icon: 'bi-filetype-raw',     group: t('audio.group.edit') },
  { id: 'transcribe', name: t('audio.functions.transcribe'), icon: 'bi-mic-fill',         group: t('audio.group.ai') },
  { id: 'separate',   name: t('audio.functions.separate'),   icon: 'bi-music-note-list',  group: t('audio.group.ai') },
  { id: 'lyrics',     name: t('audio.functions.lyrics'),     icon: 'bi-music-note-beamed',group: t('audio.group.ai') },
])

const currentFunction = ref('transcode')
const volumeGainPreview = ref(1)
const trimRange = ref<{ start: number; end: number } | null>(null)

// Toast warning when non-MIDI file is loaded in MIDI edit mode
watch([() => currentFunction.value, () => currentFileName.value], ([fn, name]) => {
  if (fn === 'midi-edit' && name && !isMidiFile.value) {
    toast.show(t('audio.midi.unsupported'), { type: 'warning', icon: 'bi-exclamation-triangle' })
  }
})

// Clear overlays when switching panels + stop MIDI playback
watch(currentFunction, (_newFn, oldFn) => {
  trimRange.value = null
  volumeGainPreview.value = 1
  expandedTrackIdx.value = null
  // Stop MIDI playback when leaving midi-edit mode
  if (oldFn === 'midi-edit') {
    midiPlayback.stop()
  }
})

const executeDisabled = computed(() => {
  if (currentFunction.value === 'transcode')  return transcodePanelRef.value?.isDisabled  ?? !hasFile.value
  if (currentFunction.value === 'cut')        return cutPanelRef.value?.isDisabled        ?? !hasFile.value
  if (currentFunction.value === 'volume')     return volumePanelRef.value?.isDisabled     ?? !hasFile.value
  if (currentFunction.value === 'transcribe') return transcribePanelRef.value?.isDisabled ?? !hasFile.value
  if (currentFunction.value === 'separate')  return separatePanelRef.value?.isDisabled  ?? !hasFile.value
  if (currentFunction.value === 'lyrics')    return lyricsPanelRef.value?.isDisabled    ?? !hasFile.value
  if (currentFunction.value === 'midi-edit') return midiEditPanelRef.value?.isDisabled  ?? !hasFile.value
  return !hasFile.value
})

const isEntryProcessing = computed(() => collection.activeEntry.value?.status === 'processing')

const executeLoading = computed(() => {
  if (isEntryProcessing.value) return true
  if (currentFunction.value === 'transcode')  return transcodePanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'cut')        return cutPanelRef.value?.isLoading        ?? false
  if (currentFunction.value === 'volume')     return volumePanelRef.value?.isLoading     ?? false
  if (currentFunction.value === 'transcribe') return transcribePanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'separate')  return separatePanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'lyrics')    return lyricsPanelRef.value?.isLoading    ?? false
  if (currentFunction.value === 'midi-edit') return midiEditPanelRef.value?.isLoading  ?? false
  return false
})

function handleExecute() {
  if (isMultiSelect.value) {
    handleMultiExecute()
  } else {
    handleSingleExecute()
  }
}

function handleSingleExecute() {
  switch (currentFunction.value) {
    case 'transcode':  transcodePanelRef.value?.execute();  break
    case 'cut':        cutPanelRef.value?.execute();        break
    case 'volume':     volumePanelRef.value?.execute();     break
    case 'transcribe': transcribePanelRef.value?.execute(); break
    case 'separate':  separatePanelRef.value?.execute();  break
    case 'lyrics':    lyricsPanelRef.value?.execute();    break
    case 'midi-edit': midiEditPanelRef.value?.execute(); break
  }
}

function handleMultiExecute() {
  const noop = () => {}
  switch (currentFunction.value) {
    case 'transcode':
      submitToAll('/audio/transcode', () => transcodePanelRef.value!.getParams(), t('audio.transcode.task_label'), 'audio.transcode', noop); break
    case 'volume':
      submitToAll('/audio/volume',    () => volumePanelRef.value!.getParams(),    t('audio.volume.task_label'),    'audio.volume',    noop); break
    case 'transcribe':
      submitToAll('/audio/transcribe',() => transcribePanelRef.value!.getParams(),t('audio.transcribe.task_label'),'audio.transcribe', noop); break
    case 'separate':
      submitToAll('/audio/separate',  () => separatePanelRef.value!.getParams(),  t('audio.separate.task_label'),  'audio.separate',  noop); break
    case 'lyrics':
      submitToAll('/audio/lyrics',    () => lyricsPanelRef.value!.getParams(),    t('audio.lyrics.task_label'),    'audio.lyrics',    noop); break
    case 'cut':
      // 剪輯每個檔案起止不同，不支援批次
      cutPanelRef.value?.execute(); break
  }
}

function formatDuration(s: number): string {
  const h   = Math.floor(s / 3600)
  const m   = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
  return `${m}:${sec.toString().padStart(2, '0')}`
}
function formatSize(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}
function formatBitrate(bps: number): string {
  if (bps < 1000) return `${bps} bps`
  if (bps < 1_000_000) return `${(bps / 1000).toFixed(0)} Kbps`
  return `${(bps / 1_000_000).toFixed(1)} Mbps`
}

const audioInfoItems = computed<InfoItem[]>(() => {
  if (audioInfo.value) {
    const a = audioInfo.value
    return [
      { icon: 'bi-clock',             label: formatDuration(a.duration) },
      { icon: 'bi-music-note-beamed', label: a.codec.toUpperCase() },
      { icon: 'bi-soundwave',         label: `${(a.sample_rate / 1000).toFixed(1)} kHz` },
      { icon: 'bi-reception-4',       label: a.channels === 1 ? 'Mono' : 'Stereo' },
      { icon: 'bi-speedometer2',      label: formatBitrate(a.bitrate) },
      { icon: 'bi-hdd',               label: formatSize(a.file_size) },
    ]
  }
  return []
})

function onDownload() {
  const fmtMap: Record<string, [string, string]> = {
    transcode:  [transcodePanelRef.value ? '' : 'mp3', '_transcoded'],
    cut:        ['', '_cut'],
    volume:     ['', '_adjusted'],
    transcribe: ['', '_transcript'],
    separate:  ['', '_separated'],
    lyrics:    ['lrc', '_lyrics'],
  }
  const [fmt, suffix] = fmtMap[currentFunction.value] ?? ['', '_output']
  handleDownload(fmt || undefined, suffix)
}

// ── Filmstrip ────────────────────────────────────────────────────────────────

const filmstripItems = computed(() =>
  collection.entriesList.value.map(e => ({
    id: e.id,
    thumbnailUrl: e.thumbnailUrl,
    status: e.status,
    progress: e.progress,
  }))
)

function onFilmstripSelect(id: string, ctrlKey: boolean) {
  collection.selectEntry(id, ctrlKey)
}

function onFilmstripRemove(id: string) {
  collection.removeEntry(id)
}

// ── Text result modal (lyrics/transcribe) ──────────────────────────
const showTextModal = ref(false)

// ── Multi-track preview (after source separation) ──────────────────
const STEM_COLORS: Record<string, string> = {
  vocals: 'rgba(192, 132, 252, 0.7)',
  drums:  'rgba(96, 165, 250, 0.7)',
  bass:   'rgba(74, 222, 128, 0.7)',
  guitar: 'rgba(251, 146, 60, 0.7)',
  piano:  'rgba(244, 114, 182, 0.7)',
  other:  'rgba(250, 204, 21, 0.7)',
}

const taskStore = useTaskStore()

// 保存分離結果（因為 currentTaskId 在 complete 後會被清掉）
const separateStemsData = ref<Array<{ name: string; fileId: string; color: string; path?: string }> | null>(null)

// 已經問過 MIDI 跳轉的 entry IDs（不重複詢問）
const _midiJumpAskedIds = new Set<string>()

function parseStemsFromHistory(entry: { historyStack: Array<{ taskType: string; meta?: unknown }> }) {
  // 從 history stack 找最後一筆 separation 結果
  for (let i = entry.historyStack.length - 1; i >= 0; i--) {
    const h = entry.historyStack[i]
    if (h.taskType !== 'audio.separate') continue
    const meta = h.meta as { output_files?: Array<{ file_id: string; stem: string; path?: string }> } | undefined
    if (!meta?.output_files?.length || !meta.output_files[0].stem) continue
    return meta.output_files.map(f => ({
      name: f.stem,
      fileId: f.file_id,
      color: STEM_COLORS[f.stem] || 'rgba(107, 114, 128, 0.5)',
      path: f.path,
    }))
  }
  return null
}

// 監聽 history stack 變化：separation 完成 → 存 stems 資料 + MIDI modal
watch(
  () => collection.activeEntry.value?.historyStack.length ?? 0,
  (newLen, oldLen) => {
    if (newLen <= oldLen) return
    const entry = collection.activeEntry.value
    if (!entry) return
    const latest = entry.historyStack.at(-1)
    if (!latest || latest.taskType !== 'audio.separate') return
    const meta = latest.meta as { output_files?: Array<{ file_id: string; stem: string; path?: string }>; midi_file_id?: string } | undefined
    if (!meta?.output_files?.length || !meta.output_files[0].stem) return
    separateStemsData.value = meta.output_files.map(f => ({
      name: f.stem,
      fileId: f.file_id,
      color: STEM_COLORS[f.stem] || 'rgba(107, 114, 128, 0.5)',
      path: f.path,
    }))
    // 只問一次 MIDI 跳轉
    if (meta.midi_file_id && !_midiJumpAskedIds.has(entry.id)) {
      _midiJumpAskedIds.add(entry.id)
      separatePanelRef.value?.onTaskComplete({ midi_file_id: meta.midi_file_id })
    }
  },
)

// 切換檔案時從 history 還原分離結果 + 停止 MIDI 播放
watch(() => collection.activeId.value, () => {
  expandedTrackIdx.value = null
  midiPlayback.stop()
  const entry = collection.activeEntry.value
  if (entry) {
    separateStemsData.value = parseStemsFromHistory(entry)
  } else {
    separateStemsData.value = null
  }
})

const separateStems = computed(() => separateStemsData.value)

// ── MIDI 跳轉 ──
async function handleJumpToMidi(midiFileId: string) {
  // 從 separation task result 取 filename
  const entry = collection.activeEntry.value
  const task = entry?.currentTaskId ? taskStore.tasks.get(entry.currentTaskId) : null
  const result = task?.result as { midi_filename?: string } | undefined
  // 也從 history meta 找
  const latestMeta = entry?.historyStack.at(-1)?.meta as { midi_filename?: string } | undefined
  const filename = result?.midi_filename ?? latestMeta?.midi_filename ?? 'output.mid'

  await addMidiEntry(midiFileId, filename)
  currentFunction.value = 'midi-edit'
}

// ── 新增空白 MIDI ──
function makeMidiThumbnail(): string {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size; canvas.height = size
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#1e293b'; ctx.fillRect(0, 0, size, size)
  ctx.fillStyle = '#64748b'; ctx.font = '48px serif'
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.fillText('\u266B', size / 2, size / 2)
  return canvas.toDataURL()
}

let blankMidiCounter = 0

async function createBlankMidi() {
  blankMidiCounter++
  const name = blankMidiCounter === 1 ? 'Untitled.mid' : `Untitled ${blankMidiCounter}.mid`
  const file = new File([new Uint8Array(0)], name, { type: 'audio/midi' })
  const entryId = await collection.addEntry(file)
  collection.updateEntry(entryId, { status: 'idle', thumbnailUrl: makeMidiThumbnail() })
  currentFunction.value = 'midi-edit'
  // 等 panel 渲染後重置 editor 為空白狀態
  await nextTick()
  if (midiEditPanelRef.value?.editor) {
    const editor = midiEditPanelRef.value.editor
    editor.tracks.value = []
    editor.selectedNoteIds.value = new Set()
    editor.activeTrackIndex.value = 0
    editor.tempo.value = 120
    editor.timeSignature.value = [4, 4]
    editor.addTrack('Track 1', 0, false)
    editor.isDirty.value = false
  }
}

// Ctrl+A / clearSelection 由 AppFilmstrip 內部處理

// ── Titlebar actions ──────────────────────────────────────────────────────
const { registerActions, clearActions, setExtraActions, clearExtraActions } = useTitlebar()

function registerTitlebar() {
  registerActions({
    canUndo: () => {
      if (currentFunction.value === 'midi-edit') return midiEditPanelRef.value?.editor.canUndo.value ?? false
      return canGoBack.value
    },
    canRedo: () => {
      if (currentFunction.value === 'midi-edit') return midiEditPanelRef.value?.editor.canRedo.value ?? false
      return canGoForward.value
    },
    canSaveAs: () => {
      if (currentFunction.value === 'midi-edit') {
        const editor = midiEditPanelRef.value?.editor
        if (!editor) return false
        return editor.isDirty.value && editor.tracks.value.some(t => t.notes.length > 0)
      }
      return hasResult.value
    },
    onUndo: () => {
      if (currentFunction.value === 'midi-edit') midiEditPanelRef.value?.editor.undo()
      else goBack()
    },
    onRedo: () => {
      if (currentFunction.value === 'midi-edit') midiEditPanelRef.value?.editor.redo()
      else goForward()
    },
    onSaveAs: async () => {
      if (currentFunction.value === 'midi-edit') {
        const panel = midiEditPanelRef.value
        const editor = panel?.editor
        if (!editor) return
        let fid = activeFileId.value
        if (!fid) {
          // New file — create first
          const res = await apiFetch('/audio/midi/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              data: {
                ticks_per_beat: editor.ticksPerBeat?.value ?? 480,
                tempo: editor.tempo.value,
                time_signature: [...editor.timeSignature.value],
                tracks: editor.tracks.value.map(t => ({
                  name: t.name, instrument: t.instrument, color: t.color,
                  volume: t.volume, pan: t.pan, muted: t.muted, is_drum: t.isDrum,
                  notes: t.notes.map(n => ({
                    pitch: n.pitch, start: n.start, duration: n.duration, velocity: n.velocity,
                  })),
                })),
              },
            }),
          })
          if (!res.ok) return
          const result = await res.json()
          fid = result.file_id
        } else {
          await editor.saveToApi(fid)
        }
        const stem = currentFileName.value.replace(/\.[^.]+$/, '') || 'Untitled'
        downloadFile(fid, `${stem}.mid`, sourceDir.value)
      } else {
        onDownload()
      }
    },
  })
}

const _activeTick = ref(0)

watchEffect(() => {
  _activeTick.value
  const actions: TitlebarExtraAction[] = []
  if (currentFunction.value === 'lyrics' || currentFunction.value === 'transcribe') {
    actions.push({
      id: 'text-preview',
      icon: 'bi-file-text',
      tooltip: t('common.view_result'),
      disabled: !textResultContent.value,
      onClick: () => { if (textResultContent.value) showTextModal.value = true },
    })
  }
  setExtraActions(actions)
})

onActivated(() => { registerTitlebar(); _activeTick.value++ })
onDeactivated(() => { clearActions(); clearExtraActions(); midiPlayback.stop() })
onMounted(() => { registerTitlebar() })
onUnmounted(() => { clearActions(); clearExtraActions() })
</script>

<template>
  <ToolLayout
    :title="$t('audio.title')"
    accept-type="audio"
    upload-icon="bi-music-note-beamed"
    :upload-label="$t('audio.upload_label')"
    :upload-hint="$t('audio.upload_hint')"
    upload-accept="audio/*"
    show-filmstrip
    :collection-size="filmstripItems.length"
    :active-file-name="currentFileName"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    @select-function="currentFunction = $event"
    @execute="handleExecute"
    @file="handleFile"
    @files="handleFiles"
    @remove-file="handleRemoveFile"
    @clear-selection="collection.clearSelection()"
  >

    <template #preview="{ file, previewUrl }">
      <div v-if="currentFunction === 'midi-edit' && isMidiFile && midiEditPanelRef?.editor && midiEditPanelRef.editor.tracks.value.length > 0" class="midi-editor-preview">
        <!-- Loading overlay -->
        <Transition name="fade">
          <div v-if="midiEditPanelRef.editor.isLoading.value" class="midi-loading-overlay">
            <div class="spinner" />
          </div>
        </Transition>
        <!-- Track bar -->
        <div class="midi-track-bar" @wheel.prevent="onTrackBarWheel">
          <div
            v-for="(track, idx) in midiEditPanelRef.editor.tracks.value"
            :key="idx"
            class="midi-track-chip"
            :class="{ 'is-active': idx === midiEditPanelRef.editor.activeTrackIndex.value }"
            :style="idx === midiEditPanelRef.editor.activeTrackIndex.value ? { '--track-color': track.color } : undefined"
            @click="midiEditPanelRef!.editor.activeTrackIndex.value = idx"
          >
            <span class="midi-track-dot" :style="{ background: track.color }" />
            <span class="midi-track-label">{{ track.name }}</span>
            <button
              class="midi-track-toggle"
              :class="{ 'is-hidden': !track.visible }"
              :title="track.visible ? $t('audio.midi.hide_track') : $t('audio.midi.show_track')"
              @click.stop="midiEditPanelRef!.editor.updateTrack(idx, { visible: !track.visible })"
            >
              <i :class="track.visible ? 'bi bi-eye-fill' : 'bi bi-eye-slash'" />
            </button>
            <button
              class="midi-track-toggle"
              :class="{ 'is-muted': track.muted }"
              :title="$t('audio.midi.mute')"
              @click.stop="midiEditPanelRef!.editor.updateTrack(idx, { muted: !track.muted })"
            >
              <i :class="track.muted ? 'bi bi-volume-mute-fill' : 'bi bi-volume-up-fill'" />
            </button>
            <button
              class="midi-track-toggle"
              :class="{ 'is-solo': track.solo }"
              :title="$t('audio.midi.solo')"
              @click.stop="toggleSolo(idx)"
            >
              <span class="midi-solo-label">S</span>
            </button>
            <button
              class="midi-track-toggle"
              :class="{ 'is-expanded': expandedTrackIdx === idx }"
              :title="$t('audio.midi.track_settings')"
              @click.stop="toggleTrackSettings(idx)"
            >
              <i class="bi bi-three-dots" />
            </button>
            <button
              class="midi-track-toggle is-delete"
              :title="$t('audio.midi.delete_track')"
              :disabled="midiEditPanelRef!.editor.tracks.value.length <= 1"
              @click.stop="removeTrack(idx)"
            >
              <i class="bi bi-x-lg" />
            </button>
          </div>
          <!-- Add track button -->
          <button class="midi-track-add" :title="$t('audio.midi.add_track')" @click="addTrack">
            <i class="bi bi-plus" />
          </button>
        </div>

        <div class="midi-editor-body">
          <!-- Track settings overlay -->
          <Transition name="track-settings">
            <div v-if="expandedTrackIdx !== null && midiEditPanelRef!.editor.tracks.value[expandedTrackIdx]" class="midi-track-settings" :key="expandedTrackIdx">
              <div class="midi-track-settings-row">
                <input
                  type="color"
                  class="midi-track-color-picker"
                  :value="midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].color"
                  @input="midiEditPanelRef!.editor.updateTrack(expandedTrackIdx!, { color: ($event.target as HTMLInputElement).value })"
                />
                <input
                  class="midi-track-settings-name"
                  :value="midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].name"
                  @input="midiEditPanelRef!.editor.updateTrack(expandedTrackIdx!, { name: ($event.target as HTMLInputElement).value })"
                />
                <AppSelect
                  class="midi-track-settings-instrument"
                  :model-value="midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].isDrum ? -1 : midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].instrument"
                  :options="instrumentOptionsWithDrum"
                  @update:model-value="onInstrumentChange(expandedTrackIdx!, $event)"
                />
              </div>
              <div class="midi-track-settings-row">
                <label class="midi-track-settings-label">{{ $t('audio.midi.volume') }}</label>
                <AppRange
                  class="midi-track-settings-slider"
                  :model-value="midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].volume"
                  :min="0" :max="127"
                  @update:model-value="midiEditPanelRef!.editor.updateTrack(expandedTrackIdx!, { volume: $event })"
                />
                <span class="midi-track-settings-value">{{ midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].volume }}</span>
                <label class="midi-track-settings-label">{{ $t('audio.midi.pan') }}</label>
                <AppRange
                  class="midi-track-settings-slider"
                  :model-value="midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].pan"
                  :min="0" :max="127"
                  @update:model-value="midiEditPanelRef!.editor.updateTrack(expandedTrackIdx!, { pan: $event })"
                />
                <span class="midi-track-settings-value">
                  {{ midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].pan }}
                  <template v-if="midiEditPanelRef!.editor.tracks.value[expandedTrackIdx].pan === 64">(C)</template>
                </span>
              </div>
            </div>
          </Transition>
          <MidiPianoRoll
            ref="pianoRollRef"
            :tracks="midiEditPanelRef.editor.tracks.value"
            :active-track-index="midiEditPanelRef.editor.activeTrackIndex.value"
            :selected-note-ids="midiEditPanelRef.editor.selectedNoteIds.value"
            :tool-mode="midiEditPanelRef.editor.toolMode.value"
            :grid-size="midiEditPanelRef.editor.gridSize.value"
            :snap-enabled="midiEditPanelRef.editor.snapEnabled.value"
            :current-beat="midiPlayback.currentBeat.value"
            :is-playing="midiPlayback.isPlaying.value"
            :tempo="midiEditPanelRef.editor.tempo.value"
            :time-signature="midiEditPanelRef.editor.timeSignature.value"
            @add-note="(p,s,d,v) => midiEditPanelRef!.editor.addNote(p,s,d,v)"
            @delete-notes="(ids) => midiEditPanelRef!.editor.deleteNotes(ids)"
            @move-notes="(ids,db,dp) => midiEditPanelRef!.editor.moveNotes(ids,db,dp)"
            @resize-notes="(ids,d) => midiEditPanelRef!.editor.resizeNotes(ids,d)"
            @select-notes="(ids,add) => { if (add) { ids.forEach(id => midiEditPanelRef!.editor.selectNote(id, true)) } else { midiEditPanelRef!.editor.selectedNoteIds.value = new Set(ids) } }"
            @clear-selection="() => midiEditPanelRef!.editor.clearSelection()"
            @play-note="(p) => midiPlayback.playNote(p, 100, 0.3, midiEditPanelRef!.editor.activeTrackIndex.value)"
            @undo="() => midiEditPanelRef!.editor.undo()"
            @redo="() => midiEditPanelRef!.editor.redo()"
            @select-all="() => midiEditPanelRef!.editor.selectAll()"
            @copy="() => midiEditPanelRef!.editor.copySelection()"
            @paste="(beat) => midiEditPanelRef!.editor.pasteAtBeat(beat)"
            @duplicate="() => midiEditPanelRef!.editor.duplicateSelection()"
          />
        </div>
        <MidiVelocityEditor
          v-if="midiEditPanelRef.editor.activeTrack.value"
          :notes="midiEditPanelRef.editor.activeTrack.value.visible ? midiEditPanelRef.editor.activeTrack.value.notes : []"
          :selected-note-ids="midiEditPanelRef.editor.selectedNoteIds.value"
          :track-color="midiEditPanelRef.editor.activeTrack.value.color"
          :scroll-x="pianoRollRef?.scrollX ?? 0"
          :zoom-x="pianoRollRef?.zoomX ?? 80"
          :grid-size="midiEditPanelRef.editor.gridSize.value"
          @update-velocity="(ids,v) => midiEditPanelRef!.editor.updateVelocity(ids,v)"
        />
        <MidiToolbar
          :is-playing="midiPlayback.isPlaying.value"
          :current-beat="midiPlayback.currentBeat.value"
          :total-beats="midiEditPanelRef.editor.getTotalBeats()"
          :loop-enabled="midiPlayback.loopEnabled.value"
          :tempo="midiEditPanelRef.editor.tempo.value"
          @play="midiPlayback.play"
          @pause="midiPlayback.pause"
          @stop="midiPlayback.stop"
          @toggle-loop="() => { midiPlayback.loopEnabled.value = !midiPlayback.loopEnabled.value }"
        />
      </div>
      <AudioMultiTrackPreview
        v-else-if="currentFunction === 'separate' && separateStems"
        :stems="separateStems"
      />
      <AudioPreview
        v-else
        :preview-url="activePreviewUrl ?? collection.activeEntry.value?.previewUrl ?? previewUrl"
        :file="collection.activeEntry.value?.file ?? file"
        :gain-preview="currentFunction === 'volume' ? volumeGainPreview : 1"
        :trim-range="currentFunction === 'cut' ? trimRange : null"
        @update:trim-range="r => { trimRange = r; cutPanelRef?.onTrimRangeUpdate(r) }"
      />
    </template>

    <template #info-bar>
      <AppMediaInfoBar
        v-if="audioInfo || isUploading"
        :items="audioInfoItems"
        :loading="isUploading && !audioInfo"
        :loading-text="$t('audio.loading')"
      />
    </template>

    <template #filmstrip>
      <AppFilmstrip
        :items="filmstripItems"
        :active-id="collection.activeId.value"
        :selected-ids="collection.selectedIds.value"
        @select="onFilmstripSelect"
        @remove="onFilmstripRemove"
        @remove-selected="ids => collection.removeEntries(ids)"
        @clear-selection="collection.clearSelection()"
        @select-all="collection.selectAll()"
      />
    </template>

    <template #settings>
      <div class="settings-form">
        <AudioTranscodePanel
          v-if="currentFunction === 'transcode'"
          ref="transcodePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <AudioCutPanel
          v-else-if="currentFunction === 'cut'"
          ref="cutPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :duration="audioInfo?.duration"
          @submit="handlePanelSubmit"
          @update:trim-range="r => trimRange = r"
        />

        <AudioVolumePanel
          v-else-if="currentFunction === 'volume'"
          ref="volumePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
          @update:gain-preview="g => volumeGainPreview = g"
        />

        <AudioTranscribePanel
          v-else-if="currentFunction === 'transcribe'"
          ref="transcribePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <AudioSeparatePanel
          v-else-if="currentFunction === 'separate'"
          ref="separatePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
          @jump-to-midi="handleJumpToMidi"
        />

        <AudioLyricsPanel
          v-else-if="currentFunction === 'lyrics'"
          ref="lyricsPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <AudioMidiEditPanel
          v-show="currentFunction === 'midi-edit'"
          ref="midiEditPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
          @create-blank="createBlankMidi"
        />
      </div>
    </template>
  </ToolLayout>

  <TextPreviewModal
    v-if="showTextModal && textResultContent"
    :text="textResultContent"
    :title="$t('audio.lyrics.result_title')"
    :filename="currentFileName.replace(/\.[^.]+$/, '.lrc')"
    @close="showTextModal = false"
  />
</template>

<style lang="scss" scoped>
.settings-form { color: var(--text-primary); }
.midi-editor-preview {
  display: flex;
  flex-direction: column;
  width: 100%;
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  align-self: stretch;
}
.midi-track-bar {
  display: flex;
  gap: 0.35rem;
  padding: 0.4rem 0.5rem;
  overflow-x: auto;
  flex-shrink: 0;
  min-width: 0;
  max-width: 100%;
  border-bottom: 1px solid var(--panel-border);
  border-radius: 8px 8px 0 0;
  background: rgba(0, 0, 0, 0.15);

  &::-webkit-scrollbar { height: 4px; }
  &::-webkit-scrollbar-track { background: transparent; }
  &::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.2); border-radius: 2px; }
  &::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.35); }
}

.midi-track-chip {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
  flex-shrink: 0;

  &:hover { background: rgba(255, 255, 255, 0.08); }
  &.is-active {
    background: color-mix(in srgb, var(--track-color, #fff) 12%, transparent);
    border-color: var(--track-color, var(--panel-border));
    box-shadow: 0 0 6px color-mix(in srgb, var(--track-color, #fff) 25%, transparent);
  }
}

.midi-track-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: all 0.15s ease;

  .is-active > & {
    width: 10px;
    height: 10px;
    box-shadow: 0 0 4px currentColor;
  }
}

.midi-track-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;

  .is-active > & { color: var(--text-primary); font-weight: 600; }
}

.midi-track-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: none;
  border: none;
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 0.7rem;
  cursor: pointer;
  padding: 0;
  transition: all 0.15s ease;

  &:hover { color: var(--text-primary); background: rgba(255, 255, 255, 0.08); }
  &.is-hidden { color: var(--text-muted); opacity: 0.5; }
  &.is-muted { color: var(--color-danger); }
  &.is-solo { color: var(--color-warning); background: color-mix(in srgb, var(--color-warning) 15%, transparent); }
  &.is-expanded { color: var(--color-accent); }
  &.is-delete {
    &:hover { color: var(--color-danger); }
    &:disabled { opacity: 0.25; pointer-events: none; }
  }
}

.midi-solo-label {
  font-size: 0.65rem;
  font-weight: 700;
  line-height: 1;
}

.midi-track-add {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: 1px dashed rgba(255, 255, 255, 0.15);
  background: none;
  color: var(--text-muted);
  font-size: 0.85rem;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;

  &:hover {
    border-color: var(--color-accent);
    color: var(--color-accent);
    background: rgba(255, 255, 255, 0.04);
  }
}

/* ── Expandable track settings (overlay) ── */
.midi-track-settings {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.5rem 0.65rem;
  border-bottom: 1px solid var(--panel-border);
  background: rgba(20, 18, 30, 0.95);
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.midi-track-settings-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.midi-track-color-picker {
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid var(--input-border);
  border-radius: 50%;
  background: none;
  cursor: pointer;
  flex-shrink: 0;
  -webkit-appearance: none;
  appearance: none;

  &::-webkit-color-swatch-wrapper { padding: 0; }
  &::-webkit-color-swatch { border: none; border-radius: 50%; }
  &::-moz-color-swatch { border: none; border-radius: 50%; }
}

.midi-track-settings-name {
  flex: 0 0 160px;
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 4px;
  color: var(--text-primary);
  outline: none;
  min-width: 0;
  box-sizing: border-box;

  &:focus { border-color: var(--color-accent); }
}

.midi-track-settings-instrument {
  flex: 1;
  min-width: 0;
}

.midi-track-settings-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.midi-track-settings-slider {
  flex: 1;
  min-width: 60px;
}

.midi-track-settings-value {
  font-size: 0.72rem;
  color: var(--text-secondary);
  min-width: 32px;
  text-align: right;
  flex-shrink: 0;
}

.midi-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  border-radius: 8px;

  .spinner {
    width: 28px;
    height: 28px;
    border: 3px solid rgba(255, 255, 255, 0.2);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ── Track settings transition ── */
.track-settings-enter-active,
.track-settings-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.track-settings-enter-from,
.track-settings-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.midi-editor-body {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}
.midi-unsupported-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: 12px;
  i {
    font-size: 48px;
    opacity: 0.4;
  }
  p {
    font-size: 14px;
  }
}
</style>
