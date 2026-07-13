<script setup lang="ts">
import { ref, computed, watch, watchEffect, nextTick, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { useI18n } from 'vue-i18n'
import ToolLayout from '@/components/ToolLayout.vue'
import AppFilmstrip from '@/components/common/AppFilmstrip.vue'
import ImagePreview from '@/components/image/ImagePreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import ToolParamHost from '@/components/params/ToolParamHost.vue'
import { METAS } from '@/components/params'
import ImageAiRemovePanel from '@/components/image/panels/ImageAiRemovePanel.vue'
import type { FilterPreview } from '@/components/image/panels/filterTypes'
import { useImageWorkspace } from '@/composables/useImageWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'
import { useExecuteStop } from '@/composables/useExecuteStop'
import { useTitlebar, type TitlebarExtraAction } from '@/composables/useTitlebar'
import { useViewHost } from '@/composables/useViewHost'
import { subfunctionsForView } from '@/agent/agentNavCatalog'
import { panelIdFor } from '@/composables/useActiveView'

const {
  hasFile, fileId, isUploading, currentFileName, imageInfo, isLoadingInfo,
  canGoBack, canGoForward, activeFileId, activePreviewUrl, hasResult, activeResultMeta,
  goBack, goForward, handleFile, handleFiles, handleRemoveFile, handlePanelSubmit,
  handleDownload, handleDownloadBatch,
  collection, activeId, selectedIds,
  handleExistingFiles,
} = useImageWorkspace()

const { submitToAll } = useMultiSubmit(collection)
const { isCanceling, requestStop } = useExecuteStop(collection)
const isMultiSelect = computed(() => selectedIds.value.size > 1)

const { t } = useI18n()

// ToolParamHost.fileInfo 型別是 Record<string, unknown>|null；ImageInfo 因為有 palette_size?
// 這個選填欄位，TS 不會幫它合成隱式 index signature（vue-tsc TS2322 "index signature is
// missing"——VideoMediaInfo/AudioInfo 皆全欄必填故無此問題，是本案第一個帶選填欄位的
// fileInfo 型別）。用一個 computed 轉型一次，供本檔所有 <ToolParamHost :file-info> 掛載點共用
// （批 4 後續工具遷移 upscale/remove_bg/crop 等也會用到同一個 imageInfo，屆時直接複用）。
const imageInfoForHost = computed<Record<string, unknown> | null>(
  () => imageInfo.value as Record<string, unknown> | null,
)


// Preview ref (exposes clearMask, exportMask, hasMask, syncToImage)
const previewRef = ref<InstanceType<typeof ImagePreview> | null>(null)
const brushSize = ref(10)
const maskToolMode = ref<'brush' | 'polygon' | 'bezier'>('brush')

// Panel refs
const convertPanelRef  = ref<InstanceType<typeof ToolParamHost>  | null>(null)
const compressPanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)
const upscalePanelRef  = ref<InstanceType<typeof ToolParamHost>  | null>(null)
const removeBgPanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)
const aiRemovePanelRef = ref<InstanceType<typeof ImageAiRemovePanel> | null>(null)
const adjustPanelRef   = ref<InstanceType<typeof ToolParamHost> | null>(null)
const filterPanelRef   = ref<InstanceType<typeof ToolParamHost> | null>(null)
const cropPanelRef     = ref<InstanceType<typeof ToolParamHost> | null>(null)
const ocrPanelRef      = ref<InstanceType<typeof ToolParamHost>      | null>(null)

// ── W2：host 泛型收斂 ──────────────────────────────────────────────────────
// toolKey↔subFunction id 對映（convert/compress/upscale/remove-bg/adjust/filter/crop/ocr
// 皆走 ToolParamHost；remove-object 是非 host 殼 ImageAiRemovePanel，不進此表）。'convert'
// 對應 toolKey 'image.convert'（命名統一小案 Task A 已正名，id 與 toolKey/後端一致）；
// 'adjust'/'filter' 共用同一 toolKey 'image.filter'（兩掛載點各自 labelKey override）。
const HOST_TOOL_KEYS: Record<string, string> = {
  convert: 'image.convert',
  compress: 'image.compress',
  upscale: 'image.upscale',
  'remove-bg': 'image.remove_bg',
  adjust: 'image.filter',
  filter: 'image.filter',
  crop: 'image.crop',
  ocr: 'image.ocr',
}
const HOST_REFS: Record<string, typeof convertPanelRef> = {
  convert: convertPanelRef,
  compress: compressPanelRef,
  upscale: upscalePanelRef,
  'remove-bg': removeBgPanelRef,
  adjust: adjustPanelRef,
  filter: filterPanelRef,
  crop: cropPanelRef,
  ocr: ocrPanelRef,
}
function hostFor(fn: string) {
  return HOST_REFS[fn]?.value ?? null
}
const subFunctions = computed(() => [
  { id: 'convert',       name: t('image.functions.convert'),       icon: 'bi-arrow-repeat',         group: t('image.group.edit') },
  { id: 'compress',      name: t('image.functions.compress'),      icon: 'bi-file-zip-fill',        group: t('image.group.edit') },
  { id: 'adjust',        name: t('image.functions.adjust'),        icon: 'bi-sliders',              group: t('image.group.edit') },
  { id: 'filter',        name: t('image.functions.filter'),        icon: 'bi-palette-fill',         group: t('image.group.edit') },
  { id: 'crop',          name: t('image.functions.crop'),          icon: 'bi-crop',                 group: t('image.group.edit') },
  { id: 'remove-bg',     name: t('image.functions.remove_bg'),     icon: 'bi-eraser-fill',          group: t('image.group.ai') },
  { id: 'remove-object', name: t('image.functions.remove_object'), icon: 'bi-magic',                group: t('image.group.ai') },
  { id: 'upscale',       name: t('image.functions.upscale'),       icon: 'bi-arrows-angle-expand',  group: t('image.group.ai') },
  { id: 'ocr',           name: t('image.functions.ocr'),           icon: 'bi-type',                 group: t('image.group.ai') },
])

const currentFunction     = ref('convert')
const filterPreviewParams = ref<FilterPreview | null>(null)

useViewHost('image', {
  currentFunction,
  setCurrentFunction: (id) => { currentFunction.value = id },
  validSubfunctions: () => subfunctionsForView('image'),
})

// ── Per-entry panel settings cache ───────────────────────────────────────────
// 統一參數元件案批 4 Task 4.2 前：存 UI 尺度 AdjustState/FilterState（panel.getState()）。
// 遷移後：改存 host 的後端尺度 params 快照（host.getParams()）——見 savePanelSettings/
// restorePanelSettings 下方註解，語意上等價（save/restore 皆走同一顆 host，尺度一致自洽）。
interface EntryPanelSettings {
  adjust?: Record<string, unknown>
  filter?: Record<string, unknown>
}
const entrySettingsCache = new Map<string, EntryPanelSettings>()

// ── Per-entry zoom cache ──────────────────────────────────────────────────────
interface ZoomState { zoomLevel: number; panX: number; panY: number }
const zoomCache = new Map<string, ZoomState>()

// ── Preview handlers ─────────────────────────────────────────────────────────
function onPreviewChange(p: FilterPreview) {
  filterPreviewParams.value = { ...p }
}

// host.getParams()/setParams()/resetToDefaults() 取代舊 panel.getState()/setState()/reset()
// （統一參數元件案批 4 Task 4.2）——host params 是後端尺度快照（brightness=1.0 而非 UI 的
// 100），與舊 UI 尺度 AdjustState/FilterState 不同，但 save/restore 都經同一顆 host 讀寫，
// 尺度自洽，不影響「離開功能保留設定、切回還原」的使用者可觀察行為。
function savePanelSettings(entryId: string) {
  const s = entrySettingsCache.get(entryId) ?? {}
  if (adjustPanelRef.value) s.adjust = adjustPanelRef.value.getParams()
  if (filterPanelRef.value) s.filter = filterPanelRef.value.getParams()
  entrySettingsCache.set(entryId, s)
}

function restorePanelSettings(entryId: string) {
  const s = entrySettingsCache.get(entryId)
  nextTick(() => {
    if (s?.adjust && adjustPanelRef.value) adjustPanelRef.value.setParams(s.adjust)
    else if (adjustPanelRef.value) adjustPanelRef.value.resetToDefaults()
    if (s?.filter && filterPanelRef.value) filterPanelRef.value.setParams(s.filter)
    else if (filterPanelRef.value) filterPanelRef.value.resetToDefaults()
  })
}

const isFilterMode   = computed(() => currentFunction.value === 'adjust' || currentFunction.value === 'filter')
const isAiRemoveMode = computed(() => currentFunction.value === 'remove-object' && hasFile.value)
const isCropMode     = computed(() => currentFunction.value === 'crop'      && hasFile.value)

const isAnimated = computed(() => {
  const fmt = imageInfo.value?.format?.toUpperCase()
  return fmt === 'GIF' || fmt === 'APNG'
})
const showAnimFilterHint = computed(() => isFilterMode.value && isAnimated.value && !!filterPreviewParams.value)
const showAnimRemoveHint = computed(() => currentFunction.value === 'remove-object' && isAnimated.value)

// ── Preview: WebGL handles real-time rendering, no backend round-trip ────────
const effectivePreviewUrl = computed(() => activePreviewUrl.value)

/** Pass filter params to ImagePreview → WebGL renders instantly on GPU */
const effectiveFilterPreview = computed<FilterPreview | null>(() => {
  if (!isFilterMode.value) return null
  return filterPreviewParams.value
})

// 裁切遮罩：由 panel emit 事件驅動，避免跨組件 ref 依賴追蹤失效
const cropOverlayVisible = ref(false)
const cropAspectRatio    = ref('free')

const showCropOverlay = computed(() => isCropMode.value && cropOverlayVisible.value)

// 離開裁切模式時重置
watch(isCropMode, (active) => {
  if (!active) cropOverlayVisible.value = false
})

watch(currentFunction, (val, oldVal) => {
  // Save settings for the panel that's about to unmount
  const id = collection.activeId.value
  if (id && (oldVal === 'adjust' || oldVal === 'filter')) {
    savePanelSettings(id)
  }

  if (val !== 'adjust' && val !== 'filter') {
    filterPreviewParams.value = null
  }

  if (val === 'remove-object') {
    nextTick(() => previewRef.value?.syncToImage())
  }

  // Restore settings for newly mounted panel
  if (id && (val === 'adjust' || val === 'filter')) {
    restorePanelSettings(id)
  }
})

// Save/restore per-entry settings when switching filmstrip entries
watch(() => collection.activeId.value, (newId, oldId) => {
  if (oldId) {
    savePanelSettings(oldId)
    // Save zoom state for the outgoing entry
    const z = previewRef.value?.getZoomState()
    if (z) zoomCache.set(oldId, z)
  }
  if (newId) {
    // Clear stale filter preview from previous entry
    filterPreviewParams.value = null
    restorePanelSettings(newId)
    // 立即重設 zoom 避免切圖時閃一下
    previewRef.value?.resetZoom()
    // 如果有快取的 zoom state，等圖片載入後還原
    const savedZoom = zoomCache.get(newId)
    if (savedZoom) {
      nextTick(() => previewRef.value?.setZoomState(savedZoom))
    }
  }
})

// 後端最終結果回來後，清除預覽狀態並重置 slider
watch(activePreviewUrl, (newUrl, oldUrl) => {
  if (newUrl !== oldUrl) {
    filterPreviewParams.value = null
    // 新圖已套用調整/濾鏡，slider 歸回預設值
    if (adjustPanelRef.value) adjustPanelRef.value.resetToDefaults()
    if (filterPanelRef.value) filterPanelRef.value.resetToDefaults()
  }
})

// ── Keyboard shortcuts ─────────────────────────────────────────────────
// Ctrl+A / clearSelection 由 AppFilmstrip 內部處理

// 顯示遮罩時同步 canvas 位置
watch(showCropOverlay, (active) => {
  if (active) nextTick(() => previewRef.value?.syncCropCanvas())
  // 不清除 cropRect — 保留使用者的調整，切回來時恢復
})

// 同步 canvas 裁切矩形 → panel（由 ImagePreview emit 事件驅動）
const canvasCropRect = ref<{ x: number; y: number; w: number; h: number } | null>(null)

// 當前圖片正在處理中（entry status） 或 任一 panel 正在提交 → 全域鎖定
const isAnyProcessing = computed(() =>
  collection.activeEntry.value?.status === 'processing'
  || (convertPanelRef.value?.isLoading ?? false)
  || (compressPanelRef.value?.isLoading ?? false)
  || (upscalePanelRef.value?.isLoading ?? false)
  || (removeBgPanelRef.value?.isLoading ?? false)
  || (aiRemovePanelRef.value?.isLoading ?? false)
  || (adjustPanelRef.value?.isLoading ?? false)
  || (filterPanelRef.value?.isLoading ?? false)
  || (cropPanelRef.value?.isLoading ?? false)
  || (ocrPanelRef.value?.isLoading ?? false),
)

const executeDisabled = computed(() => {
  if (isAnyProcessing.value) return true
  if (currentFunction.value === 'ocr') return hostFor('ocr')?.isDisabled ?? !hasFile.value
  if (currentFunction.value === 'remove-object' && isAnimated.value) return true
  // crop 寬高未填時執行鈕 disabled（host validate → isDisabled；與 VideoView crop 分支對齊）
  if (currentFunction.value === 'crop') return hostFor('crop')?.isDisabled ?? !hasFile.value
  // 其餘工具(convert/compress/upscale/remove-bg/remove-object 非動圖/adjust/filter)沿舊行為
  // 不查各自 host.isDisabled，只看通用檔案/上傳狀態——非遺漏，是本來就有的既有語意
  // （這些 meta 皆無 validate()，host.isDisabled 實質上僅剩 !fileId/isProcessing，與此處
  // fallback 條件不完全等價，貿然統一會改變 isUploading 期間的可觀察行為，故不收）。
  return !hasFile.value || !fileId.value || isUploading.value
})

const executeLoading = computed(() => {
  if (collection.activeEntry.value?.status === 'processing') return true
  if (currentFunction.value === 'remove-object') return aiRemovePanelRef.value?.isLoading ?? false
  return hostFor(currentFunction.value)?.isLoading ?? false
})

function handleExecute() {
  if (isAnyProcessing.value) return
  if (isMultiSelect.value) {
    void handleMultiExecute()
  } else {
    handleSingleExecute()
  }
}

function handleSingleExecute() {
  if (currentFunction.value === 'remove-object') {
    aiRemovePanelRef.value?.execute()
    return
  }
  hostFor(currentFunction.value)?.execute()
}

async function handleMultiExecute() {
  const noop = () => {}
  const fn = currentFunction.value
  const toolKey = HOST_TOOL_KEYS[fn]
  // remove-object(非 host 殼，需筆刷互動)/crop(META.multiSelect===false，需裁切互動)不支援批次，
  // 退回單張（沿舊行為：無 toast，直接呼叫 handleSingleExecute）。
  if (!toolKey || METAS[toolKey].multiSelect === false) {
    handleSingleExecute()
    return
  }
  const host = hostFor(fn)
  if (!host) return
  // getSubmitSpec() 一律取代舊 compress/remove-bg/ocr 的 getParams()——三者皆無 buildSubmit，
  // getSubmitSpec().payload === {...params} 與 getParams() 完全等價（僅 apiPath/labelKey/
  // taskType 從硬編字面值改讀 meta，值相同）。preflight 統一先行：無 modelRequirement 的工具
  // （compress/remove-bg/filter）恆真、upscale/ocr 與單筆 execute() 同語意。
  if ((await host.preflight()) === false) return
  const spec = host.getSubmitSpec()
  await submitToAll(spec.apiPath, () => host.getSubmitSpec().payload, t(spec.labelKey), spec.taskType, noop)
}

function onPanelSubmit(taskId: string) {
  handlePanelSubmit(taskId)
  const id = collection.activeId.value
  if (id) savePanelSettings(id)
}

// 任務完成後清除 AI 移除筆刷
watch(
  () => activeFileId.value,
  () => {
    if (isAiRemoveMode.value) previewRef.value?.clearMask()
  }
)

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const imageInfoItems = computed<InfoItem[]>(() => {
  if (!imageInfo.value) return []
  const info = imageInfo.value
  const zoom = previewRef.value?.zoomPercent ?? 100
  return [
    { icon: 'bi-aspect-ratio', label: `${info.width} × ${info.height}` },
    { icon: 'bi-file-earmark', label: info.format ?? '—' },
    { icon: 'bi-palette',      label: info.mode },
    { icon: 'bi-hdd',          label: formatSize(info.file_size) },
    { icon: 'bi-zoom-in',      label: `${zoom}%` },
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
  entrySettingsCache.delete(id)
  collection.removeEntry(id)
}

// ── Titlebar actions ──────────────────────────────────────────────────────
const { registerActions, clearActions, setExtraActions, clearExtraActions } = useTitlebar()

const isComparing = ref(false)

function registerTitlebar() {
  registerActions({
    canUndo: () => canGoBack.value,
    canRedo: () => canGoForward.value,
    canSaveAs: () => hasResult.value,
    onUndo: () => goBack(),
    onRedo: () => goForward(),
    onSaveAs: () => handleDownload(),
  })
}

// Extra actions 隨狀態動態更新
const _activeTick = ref(0)

watchEffect(() => {
  void _activeTick.value  // reactive dependency — KeepAlive 切回時強制重跑
  const actions: TitlebarExtraAction[] = []
  // 圖片對比
  const compareEnabled = hasResult.value && currentFunction.value !== 'ocr'
  actions.push({
    id: 'compare',
    icon: 'bi-layout-split',
    tooltip: t('common.compare'),
    active: isComparing.value,
    disabled: !compareEnabled,
    onClick: () => { if (compareEnabled) isComparing.value = !isComparing.value },
  })
  setExtraActions(actions)
})

onActivated(() => { registerTitlebar(); _activeTick.value++ })
onDeactivated(() => { clearActions(); clearExtraActions() })
onMounted(() => { registerTitlebar() })
onUnmounted(() => { clearActions(); clearExtraActions() })
</script>

<template>
  <ToolLayout
    :title="$t('image.title')"
    accept-type="image"
    upload-icon="bi-image"
    :upload-label="$t('image.upload_label')"
    :upload-hint="$t('image.upload_hint')"
    upload-accept="image/*"
    show-filmstrip
    :collection-size="filmstripItems.length"
    :active-file-name="currentFileName"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :is-comparing="isComparing"
    :result-preview-url="activePreviewUrl"
    :result-meta="activeResultMeta"
    :original-preview-url="collection.activeEntry.value?.previewUrl ?? null"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    :execute-canceling="isCanceling"
    :functions-locked="isAnyProcessing"
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
      <ImagePreview
        ref="previewRef"
        :preview-url="effectivePreviewUrl ?? previewUrl"
        :image-info="imageInfo"
        :is-ai-remove-mode="isAiRemoveMode"
        :brush-size="brushSize"
        :tool-mode="maskToolMode"
        :show-crop-overlay="showCropOverlay"
        :crop-aspect-ratio="cropAspectRatio"
        :filter-preview="effectiveFilterPreview"
        @crop-rect-change="canvasCropRect = $event"
      />
      <span v-if="showAnimFilterHint" class="anim-hint"><i class="bi bi-info-circle"></i> {{ $t('common.static_preview_hint') }}</span>
      <span v-else-if="showAnimRemoveHint" class="anim-hint"><i class="bi bi-info-circle"></i> {{ $t('common.remove_not_supported') }}</span>
    </template>

    <template #info-bar>
      <AppMediaInfoBar
        v-if="imageInfo || isLoadingInfo || isUploading"
        :items="imageInfoItems"
        :loading="(isLoadingInfo || isUploading) && !imageInfo"
        :loading-text="$t('image.loading')"
      />
    </template>

    <template #filmstrip>
      <AppFilmstrip
        :items="filmstripItems"
        :activeId="activeId"
        :selectedIds="selectedIds"
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
          v-if="currentFunction === 'convert'"
          ref="convertPanelRef"
          tool-key="image.convert"
          :panel-id="panelIdFor('image', 'convert')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :file-info="imageInfoForHost"
          :is-multi-select="isMultiSelect"
          @submit="onPanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'compress'"
          ref="compressPanelRef"
          tool-key="image.compress"
          :panel-id="panelIdFor('image', 'compress')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :file-info="imageInfoForHost"
          :is-multi-select="isMultiSelect"
          :result-meta="activeResultMeta"
          @submit="onPanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'upscale'"
          ref="upscalePanelRef"
          tool-key="image.upscale"
          :panel-id="panelIdFor('image', 'upscale')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          @submit="onPanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'remove-bg'"
          ref="removeBgPanelRef"
          tool-key="image.remove_bg"
          :panel-id="panelIdFor('image', 'remove-bg')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          @submit="onPanelSubmit"
        />

        <ImageAiRemovePanel
          v-else-if="currentFunction === 'remove-object'"
          ref="aiRemovePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :image-info="imageInfo"
          v-model:brush-size="brushSize"
          v-model:tool-mode="maskToolMode"
          :get-mask="() => previewRef?.exportMask() ?? null"
          :has-mask="() => previewRef?.hasMask() ?? false"
          @clear-mask="previewRef?.clearMask()"
          @submit="onPanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'adjust'"
          ref="adjustPanelRef"
          tool-key="image.filter"
          :panel-id="panelIdFor('image', 'adjust')"
          label-key="image.adjust.task_label"
          agent-execute-label="panel.adjust.execute"
          field-group="adjust"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :file-info="imageInfoForHost"
          :is-multi-select="isMultiSelect"
          @submit="onPanelSubmit"
          @preview-change="onPreviewChange"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'filter'"
          ref="filterPanelRef"
          tool-key="image.filter"
          :panel-id="panelIdFor('image', 'filter')"
          agent-execute-label="panel.filter.execute"
          field-group="filter"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :file-info="imageInfoForHost"
          :is-multi-select="isMultiSelect"
          @submit="onPanelSubmit"
          @preview-change="onPreviewChange"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'crop'"
          ref="cropPanelRef"
          tool-key="image.crop"
          :panel-id="panelIdFor('image', 'crop')"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :file-info="imageInfoForHost"
          :canvas-crop-rect="canvasCropRect"
          @submit="onPanelSubmit"
          @update:show-crop-overlay="cropOverlayVisible = $event"
          @update:aspect-ratio="cropAspectRatio = $event"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'ocr'"
          ref="ocrPanelRef"
          tool-key="image.ocr"
          :panel-id="panelIdFor('image', 'ocr')"
          persist-key="image_ocr_model"
          i18n-prefix="image.ocr"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          @submit="onPanelSubmit"
        />
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.settings-form { color: var(--text-primary); }

.anim-hint {
  position: absolute;
  top: 0.5rem;
  left: 1rem;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  pointer-events: none;
  z-index: 5;
}
</style>
