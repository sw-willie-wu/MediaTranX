<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ToolLayout from '@/components/ToolLayout.vue'
import AppFilmstrip from '@/components/common/AppFilmstrip.vue'
import ImagePreview from '@/components/image/ImagePreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import ImageConvertPanel  from '@/components/image/panels/ImageConvertPanel.vue'
import ImageUpscalePanel  from '@/components/image/panels/ImageUpscalePanel.vue'
import ImageRemoveBgPanel from '@/components/image/panels/ImageRemoveBgPanel.vue'
import ImageAiRemovePanel from '@/components/image/panels/ImageAiRemovePanel.vue'
import ImageAdjustPanel, { type AdjustState } from '@/components/image/panels/ImageAdjustPanel.vue'
import ImageFilterPanel, { type FilterState } from '@/components/image/panels/ImageFilterPanel.vue'
import ImageCropPanel     from '@/components/image/panels/ImageCropPanel.vue'
import ImageOcrPanel      from '@/components/image/panels/ImageOcrPanel.vue'
import OcrResultModal     from '@/components/image/OcrResultModal.vue'
import type { FilterPreview } from '@/components/image/panels/filterTypes'
import { useImageWorkspace } from '@/composables/useImageWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'

const {
  hasFile, fileId, isUploading, currentFileName, imageInfo, isLoadingInfo,
  aiEnvReady, canGoBack, activeFileId, activePreviewUrl, hasResult, activeResultMeta,
  goBack, checkAiEnvironment, handleFile, handleFiles, handleRemoveFile, handlePanelSubmit,
  handleDownload, handleTextDownload, textResultFileId, textResultFilename, textResultContent,
  collection, activeId, selectedIds,
} = useImageWorkspace()

const { submitToAll } = useMultiSubmit(collection)
const isMultiSelect = computed(() => selectedIds.value.size > 1)

const { t } = useI18n()


// Preview ref (exposes clearMask, exportMask, hasMask, syncToImage)
const previewRef = ref<InstanceType<typeof ImagePreview> | null>(null)
const brushSize = ref(10)
const maskToolMode = ref<'brush' | 'polygon' | 'bezier'>('brush')

// Panel refs
const convertPanelRef  = ref<InstanceType<typeof ImageConvertPanel>  | null>(null)
const upscalePanelRef  = ref<InstanceType<typeof ImageUpscalePanel>  | null>(null)
const removeBgPanelRef = ref<InstanceType<typeof ImageRemoveBgPanel> | null>(null)
const aiRemovePanelRef = ref<InstanceType<typeof ImageAiRemovePanel> | null>(null)
const adjustPanelRef   = ref<InstanceType<typeof ImageAdjustPanel>   | null>(null)
const filterPanelRef   = ref<InstanceType<typeof ImageFilterPanel>   | null>(null)
const cropPanelRef     = ref<InstanceType<typeof ImageCropPanel>     | null>(null)
const ocrPanelRef      = ref<InstanceType<typeof ImageOcrPanel>      | null>(null)
const showOcrModal     = ref(false)

const subFunctions = computed(() => [
  { id: 'convert',   name: t('image.functions.convert'),   icon: 'bi-arrow-repeat' },
  { id: 'remove-bg', name: t('image.functions.remove_bg'), icon: 'bi-eraser-fill' },
  { id: 'ai-remove', name: t('image.functions.ai_remove'), icon: 'bi-magic' },
  { id: 'upscale',   name: t('image.functions.upscale'),   icon: 'bi-arrows-angle-expand' },
  { id: 'adjust',    name: t('image.functions.adjust'),    icon: 'bi-sliders' },
  { id: 'filter',    name: t('image.functions.filter'),    icon: 'bi-palette-fill' },
  { id: 'crop',      name: t('image.functions.crop'),      icon: 'bi-crop' },
  { id: 'ocr',       name: t('image.functions.ocr'),       icon: 'bi-type' },
])

const currentFunction     = ref('convert')
const filterPreviewParams = ref<FilterPreview | null>(null)

// ── Per-entry panel settings cache ───────────────────────────────────────────
interface EntryPanelSettings {
  adjust?: AdjustState
  filter?: FilterState
}
const entrySettingsCache = new Map<string, EntryPanelSettings>()

// ── Per-entry zoom cache ──────────────────────────────────────────────────────
interface ZoomState { zoomLevel: number; panX: number; panY: number }
const zoomCache = new Map<string, ZoomState>()

// ── Preview handlers ─────────────────────────────────────────────────────────
function onPreviewChange(p: FilterPreview) {
  filterPreviewParams.value = { ...p }
}

function savePanelSettings(entryId: string) {
  const s = entrySettingsCache.get(entryId) ?? {}
  if (adjustPanelRef.value) s.adjust = adjustPanelRef.value.getState()
  if (filterPanelRef.value) s.filter = filterPanelRef.value.getState()
  entrySettingsCache.set(entryId, s)
}

function restorePanelSettings(entryId: string) {
  const s = entrySettingsCache.get(entryId)
  nextTick(() => {
    if (s?.adjust && adjustPanelRef.value) adjustPanelRef.value.setState(s.adjust)
    else if (adjustPanelRef.value) adjustPanelRef.value.reset?.()
    if (s?.filter && filterPanelRef.value) filterPanelRef.value.setState(s.filter)
    else if (filterPanelRef.value) filterPanelRef.value.reset?.()
  })
}

const isFilterMode   = computed(() => currentFunction.value === 'adjust' || currentFunction.value === 'filter')
const isAiRemoveMode = computed(() => currentFunction.value === 'ai-remove' && hasFile.value)
const isCropMode     = computed(() => currentFunction.value === 'crop'      && hasFile.value)

const isAnimated = computed(() => {
  const fmt = imageInfo.value?.format?.toUpperCase()
  return fmt === 'GIF' || fmt === 'APNG'
})
const showAnimFilterHint = computed(() => isFilterMode.value && isAnimated.value && !!filterPreviewParams.value)
const showAnimRemoveHint = computed(() => currentFunction.value === 'ai-remove' && isAnimated.value)

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

  if (val === 'upscale' || val === 'ai-remove') checkAiEnvironment(val)
  if (val === 'ai-remove') {
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
    // Restore zoom state (or reset if first visit)
    const savedZoom = zoomCache.get(newId)
    nextTick(() => {
      if (savedZoom) previewRef.value?.setZoomState(savedZoom)
      else previewRef.value?.resetZoom()
    })
  }
})

// 後端最終結果回來後，清除預覽狀態並重置 slider
watch(activePreviewUrl, (newUrl, oldUrl) => {
  if (newUrl !== oldUrl) {
    filterPreviewParams.value = null
    // 新圖已套用調整/濾鏡，slider 歸回預設值
    if (adjustPanelRef.value) adjustPanelRef.value.reset?.()
    if (filterPanelRef.value) filterPanelRef.value.reset?.()
  }
})

// ── Keyboard shortcuts ─────────────────────────────────────────────────
function handleKeyDown(e: KeyboardEvent) {
  // Ctrl+A / Cmd+A → 全選 filmstrip
  if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
    if (collection.hasEntries.value) {
      e.preventDefault()
      collection.selectAll()
    }
  }
}
onMounted(() => window.addEventListener('keydown', handleKeyDown))
onUnmounted(() => window.removeEventListener('keydown', handleKeyDown))

// 顯示遮罩時同步 canvas 位置
watch(showCropOverlay, (active) => {
  if (active) nextTick(() => previewRef.value?.syncCropCanvas())
  else previewRef.value?.clearCropRect()
})

// 同步 canvas 裁切矩形 → panel（由 ImagePreview emit 事件驅動）
const canvasCropRect = ref<{ x: number; y: number; w: number; h: number } | null>(null)

// 當前圖片正在處理中（entry status） 或 任一 panel 正在提交 → 全域鎖定
const isAnyProcessing = computed(() =>
  collection.activeEntry.value?.status === 'processing'
  || (convertPanelRef.value?.isLoading ?? false)
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
  if (currentFunction.value === 'ocr') return ocrPanelRef.value?.isDisabled ?? !hasFile.value
  if (currentFunction.value === 'ai-remove' && isAnimated.value) return true
  return !hasFile.value || !fileId.value || isUploading.value
})

const executeLoading = computed(() => {
  if (collection.activeEntry.value?.status === 'processing') return true
  if (currentFunction.value === 'convert')   return convertPanelRef.value?.isLoading   ?? false
  if (currentFunction.value === 'upscale')   return upscalePanelRef.value?.isLoading   ?? false
  if (currentFunction.value === 'remove-bg') return removeBgPanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'ai-remove') return aiRemovePanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'adjust')    return adjustPanelRef.value?.isLoading    ?? false
  if (currentFunction.value === 'filter')    return filterPanelRef.value?.isLoading    ?? false
  if (currentFunction.value === 'crop')      return cropPanelRef.value?.isLoading      ?? false
  if (currentFunction.value === 'ocr')       return ocrPanelRef.value?.isLoading       ?? false
  return false
})

function handleExecute() {
  if (isAnyProcessing.value) return
  if (isMultiSelect.value) {
    handleMultiExecute()
  } else {
    handleSingleExecute()
  }
}

function handleSingleExecute() {
  switch (currentFunction.value) {
    case 'convert':   convertPanelRef.value?.execute();  break
    case 'upscale':   upscalePanelRef.value?.execute();  break
    case 'remove-bg': removeBgPanelRef.value?.execute(); break
    case 'ai-remove': aiRemovePanelRef.value?.execute(); break
    case 'adjust':    adjustPanelRef.value?.execute();   break
    case 'filter':    filterPanelRef.value?.execute();   break
    case 'crop':      cropPanelRef.value?.execute();     break
    case 'ocr':       ocrPanelRef.value?.execute();      break
  }
}

function handleMultiExecute() {
  const noop = () => {}
  switch (currentFunction.value) {
    case 'convert':
      submitToAll('/image/convert',   () => convertPanelRef.value!.getParams(),  t('image.convert.task_label'),    'image.convert',    noop); break
    case 'upscale':
      submitToAll('/image/upscale',   () => upscalePanelRef.value!.getParams(),  t('image.upscale.task_label'),    'image.upscale',    noop); break
    case 'remove-bg':
      submitToAll('/image/remove-bg', () => removeBgPanelRef.value!.getParams(), t('image.remove_bg.task_label'), 'image.remove_bg',  noop); break
    case 'adjust':
      submitToAll('/image/filter',    () => adjustPanelRef.value!.getParams(),   t('image.adjust.task_label'),    'image.filter',     noop); break
    case 'filter':
      submitToAll('/image/filter',    () => filterPanelRef.value!.getParams(),   t('image.filter.task_label'),    'image.filter',     noop); break
    case 'ocr':
      submitToAll('/image/ocr',       () => ocrPanelRef.value!.getParams(),      t('image.ocr.task_label'),       'image.ocr',        noop); break
    // ai-remove、crop 不支援批次（需筆刷/裁切互動），退回單張
    default:
      handleSingleExecute()
  }
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
</script>

<template>
  <ToolLayout
    :title="$t('image.title')"
    accept-type="image"
    upload-icon="bi-image"
    :upload-label="$t('image.upload_label')"
    :upload-hint="$t('image.upload_hint')"
    upload-accept="image/*"
    hide-preview-tabs
    show-filmstrip
    :collection-size="filmstripItems.length"
    :active-file-name="currentFileName"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :result-preview-url="activePreviewUrl"
    :result-meta="activeResultMeta"
    :original-preview-url="collection.activeEntry.value?.previewUrl ?? null"
    :can-go-back="canGoBack"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    :functions-locked="isAnyProcessing"
    @select-function="currentFunction = $event"
    @execute="handleExecute"
    @file="handleFile"
    @files="handleFiles"
    @remove-file="handleRemoveFile"
    @download="currentFunction === 'ocr' ? handleTextDownload() : handleDownload()"
    @go-back="goBack"
  >
    <template #toolbar-extra>
      <button
        v-if="currentFunction === 'ocr' && textResultContent"
        class="toolbar-btn ocr-result-btn"
        :data-tooltip="$t('common.view_ocr_result')"
        @click="showOcrModal = true"
      >
        <i class="bi bi-file-text"></i>
      </button>
    </template>

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
        @clear-selection="collection.clearSelection()"
      />
    </template>

    <template #settings>
      <div class="settings-form">
        <ImageConvertPanel
          v-if="currentFunction === 'convert'"
          ref="convertPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :image-info="imageInfo"
          @submit="onPanelSubmit"
        />

        <ImageUpscalePanel
          v-else-if="currentFunction === 'upscale'"
          ref="upscalePanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :ai-env-ready="aiEnvReady"
          @submit="onPanelSubmit"
        />

        <ImageRemoveBgPanel
          v-else-if="currentFunction === 'remove-bg'"
          ref="removeBgPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="onPanelSubmit"
        />

        <ImageAiRemovePanel
          v-else-if="currentFunction === 'ai-remove'"
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

        <ImageAdjustPanel
          v-else-if="currentFunction === 'adjust'"
          ref="adjustPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="onPanelSubmit"
          @preview-change="onPreviewChange"
        />

        <ImageFilterPanel
          v-else-if="currentFunction === 'filter'"
          ref="filterPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="onPanelSubmit"
          @preview-change="onPreviewChange"
        />

        <ImageCropPanel
          v-else-if="currentFunction === 'crop'"
          ref="cropPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :image-info="imageInfo"
          :canvas-crop-rect="canvasCropRect"
          @submit="onPanelSubmit"
          @update:show-crop-overlay="cropOverlayVisible = $event"
          @update:aspect-ratio="cropAspectRatio = $event"
        />

        <ImageOcrPanel
          v-else-if="currentFunction === 'ocr'"
          ref="ocrPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="onPanelSubmit"
        />
      </div>
    </template>
  </ToolLayout>

  <OcrResultModal
    v-if="showOcrModal && textResultContent"
    :text="textResultContent"
    :format="ocrPanelRef?.outputFormat ?? 'md'"
    :filename="textResultFilename"
    @close="showOcrModal = false"
  />
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
