<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
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
import ImageCompressPanel from '@/components/image/panels/ImageCompressPanel.vue'
import ImageOcrPanel      from '@/components/image/panels/ImageOcrPanel.vue'
import OcrResultModal     from '@/components/image/OcrResultModal.vue'
import type { FilterPreview } from '@/components/image/panels/filterTypes'
import { useImageWorkspace } from '@/composables/useImageWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'

const {
  hasFile, fileId, isUploading, currentFileName, imageInfo, isLoadingInfo,
  aiEnvReady, canGoBack, activeFileId, activePreviewUrl, hasResult,
  goBack, checkAiEnvironment, handleFile, handleFiles, handleRemoveFile, handlePanelSubmit,
  handleDownload, handleTextDownload, textResultFileId, textResultFilename, textResultContent,
  collection, activeId, selectedIds,
} = useImageWorkspace()

const { submitToAll } = useMultiSubmit(collection)
const isMultiSelect = computed(() => selectedIds.value.size > 1)


// Preview ref (exposes clearMask, exportMask, hasMask, syncToImage)
const previewRef = ref<InstanceType<typeof ImagePreview> | null>(null)
const brushSize = ref(10)

// Panel refs
const convertPanelRef  = ref<InstanceType<typeof ImageConvertPanel>  | null>(null)
const upscalePanelRef  = ref<InstanceType<typeof ImageUpscalePanel>  | null>(null)
const removeBgPanelRef = ref<InstanceType<typeof ImageRemoveBgPanel> | null>(null)
const aiRemovePanelRef = ref<InstanceType<typeof ImageAiRemovePanel> | null>(null)
const adjustPanelRef   = ref<InstanceType<typeof ImageAdjustPanel>   | null>(null)
const filterPanelRef   = ref<InstanceType<typeof ImageFilterPanel>   | null>(null)
const cropPanelRef     = ref<InstanceType<typeof ImageCropPanel>     | null>(null)
const compressPanelRef = ref<InstanceType<typeof ImageCompressPanel> | null>(null)
const ocrPanelRef      = ref<InstanceType<typeof ImageOcrPanel>      | null>(null)
const showOcrModal     = ref(false)

const subFunctions = [
  { id: 'convert',   name: '轉檔',    icon: 'bi-arrow-repeat' },
  { id: 'remove-bg', name: '去背',    icon: 'bi-eraser-fill' },
  { id: 'ai-remove', name: '物件移除', icon: 'bi-magic' },
  { id: 'upscale',   name: '超解析',  icon: 'bi-arrows-angle-expand' },
  { id: 'adjust',    name: '調整',    icon: 'bi-sliders' },
  { id: 'filter',    name: '濾鏡',    icon: 'bi-palette-fill' },
  { id: 'crop',      name: '裁切',    icon: 'bi-crop' },
  { id: 'compress',  name: '壓縮',    icon: 'bi-file-zip-fill' },
  { id: 'ocr',       name: '文字辨識', icon: 'bi-type' },
]

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

function savePanelSettings(entryId: string) {
  const s = entrySettingsCache.get(entryId) ?? {}
  if (adjustPanelRef.value) s.adjust = adjustPanelRef.value.getState()
  if (filterPanelRef.value) s.filter = filterPanelRef.value.getState()
  entrySettingsCache.set(entryId, s)
}

function restorePanelSettings(entryId: string) {
  const s = entrySettingsCache.get(entryId)
  if (!s) return
  nextTick(() => {
    if (s.adjust && adjustPanelRef.value) adjustPanelRef.value.setState(s.adjust)
    if (s.filter && filterPanelRef.value) filterPanelRef.value.setState(s.filter)
  })
}

const isAiRemoveMode = computed(() => currentFunction.value === 'ai-remove' && hasFile.value)
const isCropMode     = computed(() => currentFunction.value === 'crop'      && hasFile.value)

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
    restorePanelSettings(newId)
    // Restore zoom state (or reset if first visit)
    const savedZoom = zoomCache.get(newId)
    nextTick(() => {
      if (savedZoom) previewRef.value?.setZoomState(savedZoom)
      else previewRef.value?.resetZoom()
    })
    // Re-apply live preview after entry switch.
    // watch(activePreviewUrl) clears filterPreviewParams when the URL changes,
    // but the panel's `preview` computed may not have changed (same settings),
    // so its watcher won't re-emit. Manually re-apply when entry has no result yet.
    nextTick(() => nextTick(() => {
      const entry = collection.entries.value.get(newId)
      const hasResult = (entry?.historyStack.length ?? 0) > 0
      if (!hasResult) {
        if (currentFunction.value === 'adjust') {
          filterPreviewParams.value = adjustPanelRef.value?.getPreview() ?? null
        } else if (currentFunction.value === 'filter') {
          filterPreviewParams.value = filterPanelRef.value?.getPreview() ?? null
        }
      }
    }))
  }
})

// 後端結果回來後清除 preview（新圖片已含效果）
watch(activePreviewUrl, (newUrl, oldUrl) => {
  if (newUrl !== oldUrl && (currentFunction.value === 'adjust' || currentFunction.value === 'filter')) {
    filterPreviewParams.value = null
  }
})

// 顯示遮罩時同步 canvas 位置
watch(showCropOverlay, (active) => {
  if (active) nextTick(() => previewRef.value?.syncCropCanvas())
  else previewRef.value?.clearCropRect()
})

// 同步 canvas 裁切矩形 → panel（由 ImagePreview emit 事件驅動）
const canvasCropRect = ref<{ x: number; y: number; w: number; h: number } | null>(null)

const executeDisabled = computed(() => {
  if (currentFunction.value === 'ocr') return ocrPanelRef.value?.isDisabled ?? !hasFile.value
  return !hasFile.value || !fileId.value || isUploading.value
})

const executeLoading = computed(() => {
  if (currentFunction.value === 'convert')   return convertPanelRef.value?.isLoading   ?? false
  if (currentFunction.value === 'upscale')   return upscalePanelRef.value?.isLoading   ?? false
  if (currentFunction.value === 'remove-bg') return removeBgPanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'ai-remove') return aiRemovePanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'adjust')    return adjustPanelRef.value?.isLoading    ?? false
  if (currentFunction.value === 'filter')    return filterPanelRef.value?.isLoading    ?? false
  if (currentFunction.value === 'crop')      return cropPanelRef.value?.isLoading      ?? false
  if (currentFunction.value === 'compress')  return compressPanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'ocr')       return ocrPanelRef.value?.isLoading       ?? false
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
    case 'convert':   convertPanelRef.value?.execute();  break
    case 'upscale':   upscalePanelRef.value?.execute();  break
    case 'remove-bg': removeBgPanelRef.value?.execute(); break
    case 'ai-remove': aiRemovePanelRef.value?.execute(); break
    case 'adjust':    adjustPanelRef.value?.execute();   break
    case 'filter':    filterPanelRef.value?.execute();   break
    case 'crop':      cropPanelRef.value?.execute();     break
    case 'compress':  compressPanelRef.value?.execute(); break
    case 'ocr':       ocrPanelRef.value?.execute();      break
  }
}

function handleMultiExecute() {
  const noop = () => {}
  switch (currentFunction.value) {
    case 'convert':
      submitToAll('/image/convert',   () => convertPanelRef.value!.getParams(),  '格式轉換',      'image.convert',    noop); break
    case 'upscale':
      submitToAll('/image/upscale',   () => upscalePanelRef.value!.getParams(),  '超解析',        'image.upscale',    noop); break
    case 'remove-bg':
      submitToAll('/image/remove-bg', () => removeBgPanelRef.value!.getParams(), '去背',          'image.remove_bg',  noop); break
    case 'adjust':
      submitToAll('/image/filter',    () => adjustPanelRef.value!.getParams(),   '圖片調整',      'image.filter',     noop); break
    case 'filter':
      submitToAll('/image/filter',    () => filterPanelRef.value!.getParams(),   '圖片濾鏡',      'image.filter',     noop); break
    case 'compress':
      submitToAll('/image/compress',  () => compressPanelRef.value!.getParams(), '圖片壓縮',      'image.compress',   noop); break
    case 'ocr':
      submitToAll('/image/ocr',       () => ocrPanelRef.value!.getParams(),      'OCR 文字辨識',  'image.ocr',        noop); break
    // ai-remove、crop 不支援批次（需筆刷/裁切互動），退回單張
    default:
      handleSingleExecute()
  }
}

function onPanelSubmit(taskId: string) {
  handlePanelSubmit(taskId)
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
    title="圖片工具"
    accept-type="image"
    upload-icon="bi-image"
    upload-label="拖曳圖片到這裡"
    upload-hint="支援 JPG、PNG、WebP、BMP 等格式"
    upload-accept="image/*"
    hide-preview-tabs
    show-filmstrip
    :collection-size="filmstripItems.length"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :result-preview-url="activePreviewUrl"
    :original-preview-url="collection.activeEntry.value?.previewUrl ?? null"
    :can-go-back="canGoBack"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
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
        data-tooltip="查看 OCR 結果"
        @click="showOcrModal = true"
      >
        <i class="bi bi-file-text"></i>
      </button>
    </template>

    <template #preview="{ previewUrl }">
      <ImagePreview
        ref="previewRef"
        :preview-url="activePreviewUrl ?? previewUrl"
        :image-info="imageInfo"
        :is-ai-remove-mode="isAiRemoveMode"
        :brush-size="brushSize"
        :show-crop-overlay="showCropOverlay"
        :crop-aspect-ratio="cropAspectRatio"
        :filter-preview="filterPreviewParams"
        @crop-rect-change="canvasCropRect = $event"
      />
    </template>

    <template #info-bar>
      <AppMediaInfoBar
        v-if="imageInfo || isLoadingInfo || isUploading"
        :items="imageInfoItems"
        :loading="(isLoadingInfo || isUploading) && !imageInfo"
        loading-text="讀取圖片資訊..."
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
          v-model:brush-size="brushSize"
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
          @preview-change="filterPreviewParams = $event"
        />

        <ImageFilterPanel
          v-else-if="currentFunction === 'filter'"
          ref="filterPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="onPanelSubmit"
          @preview-change="filterPreviewParams = $event"
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

        <ImageCompressPanel
          v-else-if="currentFunction === 'compress'"
          ref="compressPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          :image-info="imageInfo"
          @submit="onPanelSubmit"
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
</style>
