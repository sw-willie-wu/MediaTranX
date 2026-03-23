<script setup lang="ts">
import { ref, computed, watch } from 'vue'
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
import TextPreviewModal from '@/components/common/TextPreviewModal.vue'
import { useAudioWorkspace } from '@/composables/useAudioWorkspace'
import { useTaskStore } from '@/stores/tasks'

const { t } = useI18n()

const {
  hasFile, fileId, activePreviewUrl, isUploading, sourceDir, currentFileName, hasResult, audioInfo,
  textResultContent, textResultFileId,
  collection,
  handleFile, handleFiles, handleRemoveFile, handlePanelSubmit, handleDownload,
} = useAudioWorkspace()

// Panel refs
const transcodePanelRef  = ref<InstanceType<typeof AudioTranscodePanel>  | null>(null)
const cutPanelRef        = ref<InstanceType<typeof AudioCutPanel>        | null>(null)
const volumePanelRef     = ref<InstanceType<typeof AudioVolumePanel>     | null>(null)
const transcribePanelRef = ref<InstanceType<typeof AudioTranscribePanel> | null>(null)
const separatePanelRef   = ref<InstanceType<typeof AudioSeparatePanel>  | null>(null)
const lyricsPanelRef     = ref<InstanceType<typeof AudioLyricsPanel>    | null>(null)

const subFunctions = computed(() => [
  { id: 'transcode',  name: t('audio.functions.transcode'),  icon: 'bi-arrow-repeat' },
  { id: 'cut',        name: t('audio.functions.cut'),        icon: 'bi-scissors' },
  { id: 'volume',     name: t('audio.functions.volume'),     icon: 'bi-volume-up-fill' },
  { id: 'transcribe', name: t('audio.functions.transcribe'), icon: 'bi-mic-fill' },
  { id: 'separate',  name: t('audio.functions.separate'),  icon: 'bi-music-note-list' },
  { id: 'lyrics',    name: t('audio.functions.lyrics'),    icon: 'bi-music-note-beamed' },
])

const currentFunction = ref('transcode')

const executeDisabled = computed(() => {
  if (currentFunction.value === 'transcode')  return transcodePanelRef.value?.isDisabled  ?? !hasFile.value
  if (currentFunction.value === 'cut')        return cutPanelRef.value?.isDisabled        ?? !hasFile.value
  if (currentFunction.value === 'volume')     return volumePanelRef.value?.isDisabled     ?? !hasFile.value
  if (currentFunction.value === 'transcribe') return transcribePanelRef.value?.isDisabled ?? !hasFile.value
  if (currentFunction.value === 'separate')  return separatePanelRef.value?.isDisabled  ?? !hasFile.value
  if (currentFunction.value === 'lyrics')    return lyricsPanelRef.value?.isDisabled    ?? !hasFile.value
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
  return false
})

function handleExecute() {
  switch (currentFunction.value) {
    case 'transcode':  transcodePanelRef.value?.execute();  break
    case 'cut':        cutPanelRef.value?.execute();        break
    case 'volume':     volumePanelRef.value?.execute();     break
    case 'transcribe': transcribePanelRef.value?.execute(); break
    case 'separate':  separatePanelRef.value?.execute();  break
    case 'lyrics':    lyricsPanelRef.value?.execute();    break
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
  vocals: 'rgba(168, 85, 247, 0.5)',
  drums:  'rgba(59, 130, 246, 0.5)',
  bass:   'rgba(34, 197, 94, 0.5)',
  guitar: 'rgba(249, 115, 22, 0.5)',
  piano:  'rgba(236, 72, 153, 0.5)',
  other:  'rgba(107, 114, 128, 0.5)',
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
      <AudioMultiTrackPreview
        v-if="currentFunction === 'separate' && separateStems"
        :stems="separateStems"
      />
      <AudioPreview
        v-else
        :preview-url="activePreviewUrl ?? collection.activeEntry.value?.previewUrl ?? previewUrl"
        :file="collection.activeEntry.value?.file ?? file"
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
        @clear-selection="collection.clearSelection()"
        @select-all="collection.selectAll()"
      />
    </template>

    <template #settings>
      <div class="settings-form">
        <AudioTranscodePanel
          v-if="currentFunction === 'transcode'"
          ref="transcodePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <AudioCutPanel
          v-else-if="currentFunction === 'cut'"
          ref="cutPanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :duration="audioInfo?.duration"
          @submit="handlePanelSubmit"
        />

        <AudioVolumePanel
          v-else-if="currentFunction === 'volume'"
          ref="volumePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <AudioTranscribePanel
          v-else-if="currentFunction === 'transcribe'"
          ref="transcribePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :source-dir="sourceDir"
          @submit="handlePanelSubmit"
        />

        <AudioSeparatePanel
          v-else-if="currentFunction === 'separate'"
          ref="separatePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :source-dir="sourceDir"
          @submit="handlePanelSubmit"
        />

        <AudioLyricsPanel
          v-else-if="currentFunction === 'lyrics'"
          ref="lyricsPanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :source-dir="sourceDir"
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
</style>
