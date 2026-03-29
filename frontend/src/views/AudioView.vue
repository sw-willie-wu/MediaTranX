<script setup lang="ts">
import { ref, computed, watch, defineAsyncComponent } from 'vue'
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
const MidiToolbar = defineAsyncComponent(() => import('@/components/audio/midi/MidiToolbar.vue'))
const MidiPianoRoll = defineAsyncComponent(() => import('@/components/audio/midi/MidiPianoRoll.vue'))
const MidiVelocityEditor = defineAsyncComponent(() => import('@/components/audio/midi/MidiVelocityEditor.vue'))
import TextPreviewModal from '@/components/common/TextPreviewModal.vue'
import { useAudioWorkspace } from '@/composables/useAudioWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'
import { useTaskStore } from '@/stores/tasks'

const { t } = useI18n()

const {
  hasFile, fileId, activeFileId, activePreviewUrl, isUploading, sourceDir, currentFileName, hasResult, audioInfo,
  textResultContent, textResultFileId,
  collection,
  handleFile, handleFiles, handleRemoveFile, handlePanelSubmit, handleDownload,
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

const subFunctions = computed(() => [
  { id: 'transcode',  name: t('audio.functions.transcode'),  icon: 'bi-arrow-repeat',     group: t('audio.group.edit') },
  { id: 'cut',        name: t('audio.functions.cut'),        icon: 'bi-scissors',         group: t('audio.group.edit') },
  { id: 'volume',     name: t('audio.functions.volume'),     icon: 'bi-volume-up-fill',   group: t('audio.group.edit') },
  { id: 'transcribe', name: t('audio.functions.transcribe'), icon: 'bi-mic-fill',         group: t('audio.group.ai') },
  { id: 'separate',   name: t('audio.functions.separate'),   icon: 'bi-music-note-list',  group: t('audio.group.ai') },
  { id: 'lyrics',     name: t('audio.functions.lyrics'),     icon: 'bi-music-note-beamed',group: t('audio.group.ai') },
  { id: 'midi-edit',  name: t('audio.functions.midiEdit'),   icon: 'bi-music-note-beamed',group: t('audio.group.edit') },
])

const currentFunction = ref('transcode')
const volumeGainPreview = ref(1)
const trimRange = ref<{ start: number; end: number } | null>(null)

// Clear overlays when switching panels
watch(currentFunction, () => {
  trimRange.value = null
  volumeGainPreview.value = 1
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
    separate:  ['wav', '.vocals'],
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

// 監聽 task 完成，如果是 separate 就存結果
watch(
  () => {
    const entry = collection.activeEntry.value
    if (!entry?.currentTaskId) return null
    return taskStore.tasks.get(entry.currentTaskId)
  },
  (task) => {
    if (!task || task.status !== 'completed' || !task.result) return
    if (task.taskType !== 'audio.separate') return
    const r = task.result as { output_files?: Array<{ file_id: string; stem: string; path?: string }> }
    if (!r.output_files?.length || !r.output_files[0].stem) return
    separateStemsData.value = r.output_files.map(f => ({
      name: f.stem,
      fileId: f.file_id,
      color: STEM_COLORS[f.stem] || 'rgba(107, 114, 128, 0.5)',
      path: f.path,
    }))
  },
  { deep: true },
)

// 切換檔案時清除
watch(() => collection.activeId.value, () => {
  separateStemsData.value = null
})

const separateStems = computed(() => separateStemsData.value)

// Ctrl+A / clearSelection 由 AppFilmstrip 內部處理
</script>

<template>
  <ToolLayout
    :title="$t('audio.title')"
    accept-type="audio"
    upload-icon="bi-music-note-beamed"
    :upload-label="$t('audio.upload_label')"
    :upload-hint="$t('audio.upload_hint')"
    upload-accept="audio/*"
    hide-preview-tabs
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
    @download="onDownload"
    @clear-selection="collection.clearSelection()"
  >
    <template #toolbar-extra>
      <button
        v-if="(currentFunction === 'lyrics' || currentFunction === 'transcribe') && textResultContent"
        class="toolbar-btn"
        :data-tooltip="$t('common.view_result')"
        @click="showTextModal = true"
      >
        <i class="bi bi-file-text"></i>
      </button>
    </template>

    <template #preview="{ file, previewUrl }">
      <template v-if="currentFunction === 'midi-edit' && midiEditPanelRef?.editor">
        <div class="midi-editor-preview">
          <MidiToolbar
            :is-playing="midiEditPanelRef.editor.isPlaying?.value ?? false"
            :current-beat="0"
            :total-beats="midiEditPanelRef.editor.getTotalBeats()"
            :loop-enabled="false"
            :tool-mode="midiEditPanelRef.editor.toolMode.value"
            :tempo="midiEditPanelRef.editor.tempo.value"
            @play="() => {}"
            @pause="() => {}"
            @stop="() => {}"
            @toggle-loop="() => {}"
            @set-tool="(m) => midiEditPanelRef!.editor.toolMode.value = m"
          />
          <div class="midi-editor-body">
            <MidiPianoRoll
              ref="pianoRollRef"
              :tracks="midiEditPanelRef.editor.tracks.value"
              :active-track-index="midiEditPanelRef.editor.activeTrackIndex.value"
              :selected-note-ids="midiEditPanelRef.editor.selectedNoteIds.value"
              :tool-mode="midiEditPanelRef.editor.toolMode.value"
              :grid-size="midiEditPanelRef.editor.gridSize.value"
              :snap-enabled="midiEditPanelRef.editor.snapEnabled.value"
              :current-beat="0"
              :is-playing="false"
              :tempo="midiEditPanelRef.editor.tempo.value"
              :time-signature="midiEditPanelRef.editor.timeSignature.value"
              @add-note="(p,s,d,v) => midiEditPanelRef!.editor.addNote(p,s,d,v)"
              @delete-notes="(ids) => midiEditPanelRef!.editor.deleteNotes(ids)"
              @move-notes="(ids,db,dp) => midiEditPanelRef!.editor.moveNotes(ids,db,dp)"
              @resize-notes="(ids,d) => midiEditPanelRef!.editor.resizeNotes(ids,d)"
              @select-notes="(ids,add) => ids.forEach(id => midiEditPanelRef!.editor.selectNote(id,add))"
              @clear-selection="() => midiEditPanelRef!.editor.clearSelection()"
              @play-note="(p) => {}"
            />
          </div>
          <MidiVelocityEditor
            v-if="midiEditPanelRef.editor.activeTrack.value"
            :notes="midiEditPanelRef.editor.activeTrack.value.notes"
            :selected-note-ids="midiEditPanelRef.editor.selectedNoteIds.value"
            :track-color="midiEditPanelRef.editor.activeTrack.value.color"
            :scroll-x="pianoRollRef?.scrollX ?? 0"
            :zoom-x="pianoRollRef?.zoomX ?? 80"
            :grid-size="midiEditPanelRef.editor.gridSize.value"
            @update-velocity="(ids,v) => midiEditPanelRef!.editor.updateVelocity(ids,v)"
          />
        </div>
      </template>
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
          :source-dir="sourceDir"
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
          :source-dir="sourceDir"
          @submit="handlePanelSubmit"
        />

        <AudioSeparatePanel
          v-else-if="currentFunction === 'separate'"
          ref="separatePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :source-dir="sourceDir"
          @submit="handlePanelSubmit"
        />

        <AudioLyricsPanel
          v-else-if="currentFunction === 'lyrics'"
          ref="lyricsPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :source-dir="sourceDir"
          @submit="handlePanelSubmit"
        />

        <AudioMidiEditPanel
          v-if="currentFunction === 'midi-edit'"
          ref="midiEditPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
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
  height: 100%;
}
.midi-editor-body {
  flex: 1;
  min-height: 0;
}
</style>
