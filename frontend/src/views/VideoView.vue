<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { useI18n } from 'vue-i18n'
import ToolLayout from '@/components/ToolLayout.vue'
import AppFilmstrip from '@/components/common/AppFilmstrip.vue'
import VideoPreview from '@/components/video/VideoPreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import VideoTranscodePanel from '@/components/video/panels/VideoTranscodePanel.vue'
import VideoCutPanel from '@/components/video/panels/VideoCutPanel.vue'
import VideoCropPanel from '@/components/video/panels/VideoCropPanel.vue'
import SubtitlePanel from '@/components/video/SubtitlePanel.vue'
import VideoInterpolatePanel from '@/components/video/panels/VideoInterpolatePanel.vue'
import VideoEnhancePanel from '@/components/video/panels/VideoEnhancePanel.vue'
import VideoSummaryPanel from '@/components/video/panels/VideoSummaryPanel.vue'
import { useVideoWorkspace } from '@/composables/useVideoWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'
import { useExecuteStop } from '@/composables/useExecuteStop'
import { useToast } from '@/composables/useToast'
import { useTitlebar } from '@/composables/useTitlebar'
import { useViewHost } from '@/composables/useViewHost'
import { subfunctionsForView } from '@/agent/agentNavCatalog'

const { t } = useI18n()

const {
  hasFile, activeFileId, activePreviewUrl, isUploading, currentFileName, mediaInfo, hasResult,
  canGoBack, canGoForward,
  collection,
  handleFile, handleFiles, handleRemoveFile, handlePanelSubmit, handleDownload,
  handleDownloadBatch,
  handleExistingFiles,
  goBack, goForward,
} = useVideoWorkspace()

const selectedIds = computed(() => collection.selectedIds.value)
const isMultiSelect = computed(() => selectedIds.value.size > 1)
const { submitToAll } = useMultiSubmit(collection)
const { isCanceling, requestStop } = useExecuteStop(collection)
const toast = useToast()

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
const cropPanelRef = ref<InstanceType<typeof VideoCropPanel> | null>(null)
const subtitlePanelRef = ref<InstanceType<typeof SubtitlePanel> | null>(null)
const interpolatePanelRef = ref<InstanceType<typeof VideoInterpolatePanel> | null>(null)
const enhancePanelRef = ref<InstanceType<typeof VideoEnhancePanel> | null>(null)
const summaryPanelRef = ref<InstanceType<typeof VideoSummaryPanel> | null>(null)

// Crop state (shared between VideoPreview and VideoCropPanel)
const showCropOverlay = ref(false)
const cropAspectRatio = ref('free')
const canvasCropRect = ref<{ x: number; y: number; w: number; h: number } | null>(null)

const subFunctions = computed(() => [
  { id: 'transcode',   name: t('video.functions.transcode'),   icon: 'bi-arrow-repeat',   group: t('video.group.edit') },
  { id: 'cut',         name: t('video.functions.cut'),         icon: 'bi-scissors',       group: t('video.group.edit') },
  { id: 'crop',        name: t('video.functions.crop'),        icon: 'bi-crop',           group: t('video.group.edit') },
  { id: 'subtitle',    name: t('video.functions.subtitle'),    icon: 'bi-badge-cc-fill',  group: t('video.group.ai') },
  { id: 'summary',     name: t('video.functions.summary'),     icon: 'bi-card-text',      group: t('video.group.ai') },
  { id: 'interpolate', name: t('video.functions.interpolate'), icon: 'bi-speedometer2',   group: t('video.group.ai') },
  { id: 'enhance',     name: t('video.functions.enhance'),     icon: 'bi-stars',          group: t('video.group.ai') },
])

const currentFunction = ref('transcode')

useViewHost('video', {
  currentFunction,
  setCurrentFunction: (id) => { currentFunction.value = id },
  validSubfunctions: () => subfunctionsForView('video'),
})

const isEntryProcessing = computed(() => collection.activeEntry.value?.status === 'processing')

const executeDisabled = computed(() => {
  if (currentFunction.value === 'subtitle')  return subtitlePanelRef.value?.isDisabled ?? true
  if (currentFunction.value === 'transcode') return transcodePanelRef.value?.isDisabled ?? !hasFile.value
  if (currentFunction.value === 'cut')       return cutPanelRef.value?.isDisabled ?? !hasFile.value
  if (currentFunction.value === 'crop')      return cropPanelRef.value?.isDisabled ?? !hasFile.value
  if (currentFunction.value === 'summary')   return summaryPanelRef.value?.isDisabled ?? true
  return !hasFile.value
})

const executeLoading = computed(() => {
  if (isEntryProcessing.value) return true
  if (currentFunction.value === 'subtitle')  return subtitlePanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'transcode') return transcodePanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'cut')       return cutPanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'crop')      return cropPanelRef.value?.isLoading ?? false
  if (currentFunction.value === 'summary')   return summaryPanelRef.value?.isLoading ?? false
  return false
})

function handleExecute() {
  if (isMultiSelect.value) {
    void handleMultiExecute()
  } else {
    handleSingleExecute()
  }
}

function handleSingleExecute() {
  switch (currentFunction.value) {
    case 'transcode':   transcodePanelRef.value?.execute(); break
    case 'cut':         cutPanelRef.value?.execute(); break
    case 'crop':        cropPanelRef.value?.execute(); break
    case 'subtitle':    subtitlePanelRef.value?.submitGenerate(); break
    case 'summary':     summaryPanelRef.value?.execute(); break
    case 'interpolate': interpolatePanelRef.value?.execute(); break
    case 'enhance':     enhancePanelRef.value?.execute(); break
  }
}

async function handleMultiExecute() {
  const noop = () => {}
  switch (currentFunction.value) {
    case 'transcode':
      await submitToAll('/video/transcode', () => transcodePanelRef.value!.getParams(), t('video.transcode.task_label'), 'video.transcode', noop); break
    case 'summary':
      if (await summaryPanelRef.value?.preflight() === false) break
      await submitToAll('/video/summary', () => summaryPanelRef.value!.getParams(), t('video.summary.task_label'), 'video.summary', noop); break
    case 'interpolate':
      if (await interpolatePanelRef.value?.preflight() === false) break
      await submitToAll('/video/interpolate', () => interpolatePanelRef.value!.getParams(), t('video.interpolate.task_label'), 'video.interpolate', noop); break
    case 'enhance':
      if (await enhancePanelRef.value?.preflight() === false) break
      await submitToAll('/video/enhance', () => enhancePanelRef.value!.getParams(), t('video.enhance.task_label'), 'video.enhance', noop); break
    case 'cut':
    case 'crop':
    case 'subtitle':
      // 互動型工具不支援批次(座標/時間軸 per-file):明示並只跑目前檔案
      toast.show(t('video.multi_not_supported'), { type: 'info', icon: 'bi-info-circle' })
      handleSingleExecute(); break
  }
}

function onDownload() {
  const fmt = transcodePanelRef.value?.outputFormat ?? 'mp4'
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
    { icon: m.audio_codec ? 'bi-volume-up' : 'bi-volume-mute', label: m.audio_codec ? m.audio_codec.toUpperCase() : 'N/A' },
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

// ── Titlebar actions ──────────────────────────────────────────────────────
const { registerActions, clearActions } = useTitlebar()

function registerTitlebar() {
  registerActions({
    canUndo: () => canGoBack.value,
    canRedo: () => canGoForward.value,
    canSaveAs: () => hasResult.value,
    onUndo: () => goBack(),
    onRedo: () => goForward(),
    onSaveAs: () => onDownload(),
  })
}

onActivated(() => { registerTitlebar() })
onDeactivated(() => { clearActions() })
onMounted(() => { registerTitlebar() })
onUnmounted(() => { clearActions() })
</script>

<template>
  <ToolLayout
    :title="$t('video.title')"
    accept-type="video"
    upload-icon="bi-film"
    :upload-label="$t('video.upload_label')"
    :upload-hint="$t('video.upload_hint')"
    upload-accept="video/*"
    show-filmstrip
    :collection-size="filmstripItems.length"
    :active-file-name="currentFileName"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    :execute-canceling="isCanceling"
    @select-function="currentFunction = $event"
    @execute="handleExecute"
    @stop="requestStop"
    @file="handleFile"
    @files="handleFiles"
    @existing-files="handleExistingFiles"
    @remove-file="handleRemoveFile"
    @clear-selection="collection.clearSelection()"
  >
    <template #preview="{ previewUrl }">
      <VideoPreview
        :preview-url="activePreviewUrl ?? collection.activeEntry.value?.previewUrl ?? previewUrl"
        :media-info="mediaInfo"
        :current-function="currentFunction"
        v-model:start-time="cutStartTime"
        v-model:end-time="cutEndTime"
        :show-crop-overlay="showCropOverlay && currentFunction === 'crop'"
        :crop-aspect-ratio="cropAspectRatio"
        @crop-rect-change="canvasCropRect = $event"
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
        @batch-save="handleDownloadBatch"
      />
    </template>

    <template #settings>
      <div class="settings-form">
        <VideoTranscodePanel
          v-if="currentFunction === 'transcode'"
          ref="transcodePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
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
          :is-multi-select="isMultiSelect"
          @submit="handlePanelSubmit"
        />

        <VideoCropPanel
          v-else-if="currentFunction === 'crop'"
          ref="cropPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :video-size="mediaInfo ? { width: mediaInfo.width, height: mediaInfo.height } : null"
          :canvas-crop-rect="canvasCropRect"
          @submit="handlePanelSubmit"
          @update:show-crop-overlay="showCropOverlay = $event"
          @update:aspect-ratio="cropAspectRatio = $event"
        />

        <div v-else-if="currentFunction === 'subtitle'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-badge-cc-fill me-2"></i>{{ $t('video.subtitle.title') }}</h6>
          <SubtitlePanel
            ref="subtitlePanelRef"
            :fileId="activeFileId"
            :mediaInfo="mediaInfo"
            @submit="handlePanelSubmit"
          />
        </div>
        <!-- Note: SubtitlePanel does not accept :isMultiSelect (m16 — subtitle panel hardcodes false internally) -->

        <VideoInterpolatePanel
          v-else-if="currentFunction === 'interpolate'"
          ref="interpolatePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :media-info="mediaInfo"
          :is-multi-select="isMultiSelect"
          @submit="handlePanelSubmit"
        />

        <VideoSummaryPanel
          v-else-if="currentFunction === 'summary'"
          ref="summaryPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          @submit="handlePanelSubmit"
        />

        <VideoEnhancePanel
          v-else-if="currentFunction === 'enhance'"
          ref="enhancePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :media-info="mediaInfo"
          :is-multi-select="isMultiSelect"
          @submit="handlePanelSubmit"
        />
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
