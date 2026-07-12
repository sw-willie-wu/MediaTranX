<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { useI18n } from 'vue-i18n'
import ToolLayout from '@/components/ToolLayout.vue'
import AppFilmstrip from '@/components/common/AppFilmstrip.vue'
import VideoPreview from '@/components/video/VideoPreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import ToolParamHost from '@/components/params/ToolParamHost.vue'
import { METAS } from '@/components/params'
import SubtitlePanel from '@/components/video/SubtitlePanel.vue'
import { useVideoWorkspace } from '@/composables/useVideoWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'
import { useExecuteStop } from '@/composables/useExecuteStop'
import { useToast } from '@/composables/useToast'
import { useTitlebar } from '@/composables/useTitlebar'
import { useViewHost } from '@/composables/useViewHost'
import { panelIdFor } from '@/composables/useActiveView'
import { subfunctionsForView } from '@/agent/agentNavCatalog'
import { parseTimeToSeconds, secondsToTime } from '@/components/params/video/cut.meta'

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

// Panel refs
const transcodePanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)
const cutPanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)
const cropPanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)
const subtitlePanelRef = ref<InstanceType<typeof SubtitlePanel> | null>(null)
const interpolatePanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)
const enhancePanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)
const summaryPanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)

// ── W2：host 泛型收斂 ──────────────────────────────────────────────────────
// toolKey↔subFunction id 對映（transcode/cut/crop/interpolate/enhance/summary 皆走
// ToolParamHost；subtitle 是非 host 殼 SubtitlePanel，不進此表）。hostFor() 供
// execute/disabled/loading/multi 四組 switch 共用單一入口。
const HOST_TOOL_KEYS: Record<string, string> = {
  transcode: 'video.transcode',
  cut: 'video.cut',
  crop: 'video.crop',
  interpolate: 'video.interpolate',
  enhance: 'video.enhance',
  summary: 'video.summary',
}
const HOST_REFS: Record<string, typeof transcodePanelRef> = {
  transcode: transcodePanelRef,
  cut: cutPanelRef,
  crop: cropPanelRef,
  interpolate: interpolatePanelRef,
  enhance: enhancePanelRef,
  summary: summaryPanelRef,
}
function hostFor(fn: string) {
  return HOST_REFS[fn]?.value ?? null
}

// Crop state (shared between VideoPreview and CropParams, bridged via ToolParamHost attrs fallthrough)
const showCropOverlay = ref(false)
const cropAspectRatio = ref('free')
const canvasCropRect = ref<{ x: number; y: number; w: number; h: number } | null>(null)

// Cut time points 橋接：VideoPreview 走 HH:MM:SS 字串契約（不動），host 內部走秒數（後端詞彙）。
// get 讀 host.params.{start,end}_time（秒）轉字串；set 把 VideoPreview 拖曳寫回的字串轉秒後
// 經 setField 寫回 host（agent 寫入路徑同一入口，維持單一事實來源）。
const cutStart = computed({
  get: () => secondsToTime(cutPanelRef.value?.params?.start_time as number | undefined),
  set: (v: string) => cutPanelRef.value?.setField('start_time', parseTimeToSeconds(v)),
})
const cutEnd = computed({
  get: () => secondsToTime(cutPanelRef.value?.params?.end_time as number | undefined),
  set: (v: string) => cutPanelRef.value?.setField('end_time', parseTimeToSeconds(v)),
})

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
  if (currentFunction.value === 'subtitle') return subtitlePanelRef.value?.isDisabled ?? true
  // summary 的無 host 時退回值是 true（非 !hasFile.value）——沿舊分支語意保留，非統一收斂遺漏。
  const fallback = currentFunction.value === 'summary' ? true : !hasFile.value
  return hostFor(currentFunction.value)?.isDisabled ?? fallback
})

const executeLoading = computed(() => {
  if (isEntryProcessing.value) return true
  if (currentFunction.value === 'subtitle') return subtitlePanelRef.value?.isLoading ?? false
  return hostFor(currentFunction.value)?.isLoading ?? false
})

function handleExecute() {
  if (isMultiSelect.value) {
    void handleMultiExecute()
  } else {
    handleSingleExecute()
  }
}

function handleSingleExecute() {
  if (currentFunction.value === 'subtitle') {
    subtitlePanelRef.value?.submitGenerate()
    return
  }
  hostFor(currentFunction.value)?.execute()
}

async function handleMultiExecute() {
  const noop = () => {}
  const fn = currentFunction.value
  const toolKey = HOST_TOOL_KEYS[fn]
  // 互動型工具(座標/時間軸 per-file)或非 host 殼(subtitle)不支援批次：明示並只跑目前檔案。
  // multiSelect gate 查 META（cut/crop 為 false）；subtitle 不在 HOST_TOOL_KEYS 表內同樣落此分支。
  if (!toolKey || METAS[toolKey].multiSelect === false) {
    toast.show(t('video.multi_not_supported'), { type: 'info', icon: 'bi-info-circle' })
    handleSingleExecute()
    return
  }
  const host = hostFor(fn)
  if (!host) return
  // preflight 統一先行：video.transcode 無 modelRequirement 恆真、summary/interpolate/enhance
  // 沿舊各自 preflight() 呼叫——語意等價（見 task report）。
  if ((await host.preflight()) === false) return
  const spec = host.getSubmitSpec()
  await submitToAll(spec.apiPath, () => host.getSubmitSpec().payload, t(spec.labelKey), spec.taskType, noop)
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
        v-model:start-time="cutStart"
        v-model:end-time="cutEnd"
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
        <ToolParamHost
          v-if="currentFunction === 'transcode'"
          ref="transcodePanelRef"
          tool-key="video.transcode"
          :panel-id="panelIdFor('video', 'transcode')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          :file-info="mediaInfo"
          @submit="handlePanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'cut'"
          ref="cutPanelRef"
          tool-key="video.cut"
          :panel-id="panelIdFor('video', 'cut')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          :file-info="mediaInfo"
          @submit="handlePanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'crop'"
          ref="cropPanelRef"
          tool-key="video.crop"
          :panel-id="panelIdFor('video', 'crop')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          :file-info="mediaInfo"
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

        <ToolParamHost
          v-else-if="currentFunction === 'interpolate'"
          ref="interpolatePanelRef"
          tool-key="video.interpolate"
          :panel-id="panelIdFor('video', 'interpolate')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          :file-info="mediaInfo"
          @submit="handlePanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'summary'"
          ref="summaryPanelRef"
          tool-key="video.summary"
          :panel-id="panelIdFor('video', 'summary')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          :file-info="mediaInfo"
          @submit="handlePanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'enhance'"
          ref="enhancePanelRef"
          tool-key="video.enhance"
          :panel-id="panelIdFor('video', 'enhance')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          :file-info="mediaInfo"
          @submit="handlePanelSubmit"
        />
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.settings-form { color: var(--text-primary); }

// .function-settings / .settings-title 由 tool-panels-shared.scss 提供（SubtitlePanel 靜態
// import 時非 scoped @use 注入全域），不在 View 層重複定義（FRONTEND_DEVELOP_SPEC §24）。
</style>
