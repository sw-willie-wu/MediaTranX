<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import ImagePreview from '@/components/image/ImagePreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import ImageConvertPanel  from '@/components/image/panels/ImageConvertPanel.vue'
import ImageUpscalePanel  from '@/components/image/panels/ImageUpscalePanel.vue'
import ImageRemoveBgPanel from '@/components/image/panels/ImageRemoveBgPanel.vue'
import ImageAiRemovePanel from '@/components/image/panels/ImageAiRemovePanel.vue'
import ImageFilterPanel   from '@/components/image/panels/ImageFilterPanel.vue'
import ImageCropPanel     from '@/components/image/panels/ImageCropPanel.vue'
import ImageCompressPanel from '@/components/image/panels/ImageCompressPanel.vue'
import ImageOcrPanel      from '@/components/image/panels/ImageOcrPanel.vue'
import OcrResultModal     from '@/components/image/OcrResultModal.vue'
import { useImageWorkspace } from '@/composables/useImageWorkspace'

const {
  hasFile, fileId, isUploading, currentFileName, imageInfo, isLoadingInfo,
  aiEnvReady, canGoBack, activeFileId, activePreviewUrl, hasResult,
  goBack, checkAiEnvironment, handleFile, handleRemoveFile, handlePanelSubmit,
  handleDownload, handleTextDownload, textResultFileId, textResultFilename, textResultContent,
} = useImageWorkspace()


// Preview ref (exposes clearMask, exportMask, hasMask, brushSize)
const previewRef = ref<InstanceType<typeof ImagePreview> | null>(null)

// Panel refs
const convertPanelRef  = ref<InstanceType<typeof ImageConvertPanel>  | null>(null)
const upscalePanelRef  = ref<InstanceType<typeof ImageUpscalePanel>  | null>(null)
const removeBgPanelRef = ref<InstanceType<typeof ImageRemoveBgPanel> | null>(null)
const aiRemovePanelRef = ref<InstanceType<typeof ImageAiRemovePanel> | null>(null)
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
  { id: 'filter',    name: '濾鏡',    icon: 'bi-palette-fill' },
  { id: 'crop',      name: '裁切',    icon: 'bi-crop' },
  { id: 'compress',  name: '壓縮',    icon: 'bi-file-zip-fill' },
  { id: 'ocr',       name: '文字辨識', icon: 'bi-type' },
]

const currentFunction = ref('convert')

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

watch(currentFunction, (val) => {
  if (val === 'upscale' || val === 'ai-remove') checkAiEnvironment(val)
  if (val === 'ai-remove') {
    nextTick(() => previewRef.value?.syncToImage())
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
  if (currentFunction.value === 'filter')    return filterPanelRef.value?.isLoading    ?? false
  if (currentFunction.value === 'crop')      return cropPanelRef.value?.isLoading      ?? false
  if (currentFunction.value === 'compress')  return compressPanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'ocr')       return ocrPanelRef.value?.isLoading       ?? false
  return false
})

function handleExecute() {
  switch (currentFunction.value) {
    case 'convert':   convertPanelRef.value?.execute();  break
    case 'upscale':   upscalePanelRef.value?.execute();  break
    case 'remove-bg': removeBgPanelRef.value?.execute(); break
    case 'ai-remove': aiRemovePanelRef.value?.execute(); break
    case 'filter':    filterPanelRef.value?.execute();   break
    case 'crop':      cropPanelRef.value?.execute();     break
    case 'compress':  compressPanelRef.value?.execute(); break
    case 'ocr':       ocrPanelRef.value?.execute();      break
  }
}

function onPanelSubmit(taskId: string) {
  handlePanelSubmit(taskId)
  // 任務完成後清除筆刷（由 workspace watch 觸發，這裡無需重複）
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
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :result-preview-url="activePreviewUrl"
    :can-go-back="canGoBack"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    @select-function="currentFunction = $event"
    @execute="handleExecute"
    @file="handleFile"
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
        :show-crop-overlay="showCropOverlay"
        :crop-aspect-ratio="cropAspectRatio"
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
          :brush-size="previewRef?.brushSize.value ?? 10"
          :get-mask="() => previewRef?.exportMask() ?? null"
          :has-mask="() => previewRef?.hasMask() ?? false"
          @update:brush-size="v => previewRef && (previewRef.brushSize.value = v)"
          @clear-mask="previewRef?.clearMask()"
          @submit="onPanelSubmit"
        />

        <ImageFilterPanel
          v-else-if="currentFunction === 'filter'"
          ref="filterPanelRef"
          :file-id="activeFileId"
          :current-file-name="currentFileName"
          @submit="onPanelSubmit"
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
