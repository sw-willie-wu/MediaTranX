<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ToolLayout from '@/components/ToolLayout.vue'
import AppFilmstrip from '@/components/common/AppFilmstrip.vue'
import VideoPreview from '@/components/video/VideoPreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import VideoTranscodePanel from '@/components/video/panels/VideoTranscodePanel.vue'
import VideoCutPanel from '@/components/video/panels/VideoCutPanel.vue'
import SubtitlePanel from '@/components/video/SubtitlePanel.vue'
import { useVideoWorkspace } from '@/composables/useVideoWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'

const { t } = useI18n()

const {
  hasFile, fileId, activeFileId, activePreviewUrl, isUploading, sourceDir, currentFileName, mediaInfo, hasResult,
  collection,
  handleFile, handleFiles, handleRemoveFile, handlePanelSubmit, handleDownload,
} = useVideoWorkspace()

const selectedIds = computed(() => collection.selectedIds.value)
const isMultiSelect = computed(() => selectedIds.value.size > 1)
const { isSubmitting, submitToAll } = useMultiSubmit(collection)

// Cut time points (shared between VideoPreview and VideoCutPanel)
const cutStartTime = ref('00:00:00')
const cutEndTime = ref('00:00:00')
const cutStreamCopy = ref(true)

watch(mediaInfo, (info) => {
  if (info) {
    const h = Math.floor(info.duration / 3600)
    const m = Math.floor((info.duration % 3600) / 60)
    const s = Math.floor(info.duration % 60)
    cutEndTime.value = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }
})

// Panel refs
const transcodePanelRef = ref<InstanceType<typeof VideoTranscodePanel> | null>(null)
const cutPanelRef = ref<InstanceType<typeof VideoCutPanel> | null>(null)
const subtitlePanelRef = ref<InstanceType<typeof SubtitlePanel> | null>(null)

const subFunctions = computed(() => [
  { id: 'transcode', name: t('video.functions.transcode'), icon: 'bi-arrow-repeat',   group: t('video.group.edit') },
  { id: 'cut',       name: t('video.functions.cut'),       icon: 'bi-scissors',       group: t('video.group.edit') },
  { id: 'subtitle',  name: t('video.functions.subtitle'),  icon: 'bi-badge-cc-fill',  group: t('video.group.ai') },
])

const currentFunction = ref('transcode')

const isEntryProcessing = computed(() => collection.activeEntry.value?.status === 'processing')

const executeDisabled = computed(() => {
  if (currentFunction.value === 'subtitle')  return subtitlePanelRef.value?.isDisabled ?? true
  if (currentFunction.value === 'transcode') return transcodePanelRef.value?.isDisabled ?? !hasFile.value
  if (currentFunction.value === 'cut')       return cutPanelRef.value?.isDisabled ?? !hasFile.value
  return !hasFile.value
})

const executeLoading = computed(() => {
  if (isEntryProcessing.value) return true
  if (currentFunction.value === 'subtitle')  return subtitlePanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'transcode') return transcodePanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'cut')       return cutPanelRef.value?.isLoading ?? false
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
    case 'transcode': transcodePanelRef.value?.execute(); break
    case 'cut':       cutPanelRef.value?.execute(); break
    case 'subtitle':  subtitlePanelRef.value?.submitGenerate(); break
  }
}

function handleMultiExecute() {
  const noop = () => {}
  switch (currentFunction.value) {
    case 'transcode':
      submitToAll('/video/transcode', () => transcodePanelRef.value!.getParams(), t('video.transcode.task_label'), 'video.transcode', noop); break
    case 'cut':
      // Cut uses per-file start/end times, not supported for batch
      cutPanelRef.value?.execute(); break
    case 'subtitle':
      // Subtitle has complex per-file state, not supported for batch
      subtitlePanelRef.value?.submitGenerate(); break
  }
}

const isProcessing = ref(false)
function handleSubtitleSubmit()  { isProcessing.value = true }
function handleSubtitleComplete() { isProcessing.value = false }

function onDownload() {
  const fmt = transcodePanelRef.value?.outputFormat ?? 'mp4'
  const isAudio = transcodePanelRef.value?.isAudioFormat ?? false
  const suffix = currentFunction.value === 'cut' ? '_cut' : '_transcoded'
  handleDownload(fmt, suffix)
}

function formatDuration(s: number) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
  return `${m}:${sec.toString().padStart(2, '0')}`
}
function formatSize(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`
  return `${(b / 1024 ** 3).toFixed(2)} GB`
}
function formatBitrate(kbps: number) {
  if (kbps < 1000) return `${kbps} Kbps`
  return `${(kbps / 1000).toFixed(1)} Mbps`
}

const mediaInfoItems = computed<InfoItem[]>(() => {
  if (!mediaInfo.value) return []
  const m = mediaInfo.value
  return [
    { icon: 'bi-aspect-ratio',  label: `${m.width}x${m.height}` },
    { icon: 'bi-clock',         label: formatDuration(m.duration) },
    { icon: 'bi-film',          label: m.video_codec.toUpperCase() },
    { icon: 'bi-volume-up',     label: m.audio_codec.toUpperCase() },
    { icon: 'bi-speedometer2',  label: formatBitrate(m.bitrate) },
    { icon: 'bi-camera-reels',  label: `${m.fps.toFixed(1)} fps` },
    { icon: 'bi-hdd',           label: formatSize(m.file_size) },
  ]
})

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
</script>

<template>
  <ToolLayout
    :title="$t('video.title')"
    accept-type="video"
    upload-icon="bi-film"
    :upload-label="$t('video.upload_label')"
    :upload-hint="$t('video.upload_hint')"
    upload-accept="video/*"
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
    <template #preview="{ previewUrl }">
      <VideoPreview
        :preview-url="activePreviewUrl ?? collection.activeEntry.value?.previewUrl ?? previewUrl"
        :media-info="mediaInfo"
        :current-function="currentFunction"
        v-model:start-time="cutStartTime"
        v-model:end-time="cutEndTime"
      />
    </template>

    <template #info-bar>
      <AppMediaInfoBar
        v-if="mediaInfo || isUploading"
        :items="mediaInfoItems"
        :loading="isUploading && !mediaInfo"
        :loading-text="$t('video.loading')"
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
        <VideoTranscodePanel
          v-if="currentFunction === 'transcode'"
          ref="transcodePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <VideoCutPanel
          v-else-if="currentFunction === 'cut'"
          ref="cutPanelRef"
          :file-id="activeFileId"
          :current-file-name="''"
          v-model:start-time="cutStartTime"
          v-model:end-time="cutEndTime"
          v-model:stream-copy="cutStreamCopy"
          @submit="handlePanelSubmit"
        />

        <div v-else-if="currentFunction === 'subtitle'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-badge-cc-fill me-2"></i>{{ $t('video.subtitle.title') }}</h6>
          <SubtitlePanel
            ref="subtitlePanelRef"
            :fileId="activeFileId"
            :mediaInfo="mediaInfo"
            :source-dir="sourceDir"
            @submit="handleSubtitleSubmit"
            @complete="handleSubtitleComplete"
          />
        </div>
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.settings-form { color: var(--text-primary); }

.function-settings {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.settings-title {
  display: flex;
  align-items: center;
  font-size: 1rem;
  font-weight: 500;
  margin: 0;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--panel-border);
}
</style>
