<script setup lang="ts">
import { ref, computed, toRef, watch, nextTick } from 'vue'
import { useImageZoom } from '@/composables/useImageZoom'
import { useCanvasMask } from '@/composables/useCanvasMask'
import { useCropRect } from '@/composables/useCropRect'
import type { ImageInfo } from '@/composables/useImageWorkspace'

const props = defineProps<{
  previewUrl: string | null
  imageInfo: ImageInfo | null
  isAiRemoveMode: boolean
  showCropOverlay: boolean
  cropAspectRatio?: string
}>()

const emit = defineEmits<{
  'canvas-ready': [exportFn: () => ImageData | null, hasMask: Readonly<{ value: boolean }>, brushSize: Readonly<{ value: number }>, clearFn: () => void]
  'brush-size-change': [size: number]
  'crop-rect-change': [rect: { x: number; y: number; w: number; h: number } | null]
}>()

// ── Refs ────────────────────────────────────────────────────────────────
const imgRef = ref<HTMLImageElement | null>(null)
const containerRef = ref<HTMLElement | null>(null)

// ── Zoom/Pan ─────────────────────────────────────────────────────────────
const { zoomLevel, panX, panY, isDragging, zoomPercent, reset, onWheel, onImageLoad, onMouseDown } =
  useImageZoom(imgRef, containerRef)

// ── Canvas Mask ──────────────────────────────────────────────────────────
const {
  canvasRef: maskCanvasRef,
  brushSize,
  syncToImage,
  onMouseDown: onCanvasMouseDown,
  onMouseMove: onCanvasMouseMove,
  onMouseUp: onCanvasMouseUp,
  onMouseLeave: onCanvasMouseLeave,
  clearMask,
  hasMask,
  exportMask,
} = useCanvasMask(imgRef, containerRef)

// ── Crop Rect ─────────────────────────────────────────────────────────────
const cropAspectRatioRef = computed(() => props.cropAspectRatio ?? 'free')
const {
  canvasRef: cropCanvasRef,
  cropRect,
  syncToImage: syncCropCanvas,
  repositionCanvas: repositionCropCanvas,
  onMouseDown: onCropMouseDown,
  onMouseMove: onCropMouseMove,
  onMouseUp: onCropMouseUp,
  onMouseLeave: onCropMouseLeave,
  clearRect: clearCropRect,
} = useCropRect(imgRef, containerRef, cropAspectRatioRef)

// 縮放/拖曳時重新定位裁切 canvas
watch([zoomLevel, panX, panY], () => {
  if (props.showCropOverlay) nextTick(() => repositionCropCanvas())
})

// 裁切矩形變動時通知父層
watch(cropRect, (rect) => {
  emit('crop-rect-change', rect ?? null)
})

defineExpose({
  clearMask, exportMask, hasMask, brushSize, syncToImage,
  cropRect, clearCropRect, syncCropCanvas,
  isAiRemoveActive: () => props.isAiRemoveMode, zoomPercent,
})

function handleImageLoad() {
  onImageLoad()
  if (props.isAiRemoveMode) syncToImage()
  if (props.showCropOverlay) syncCropCanvas()
}

function handleMouseDown(e: MouseEvent) {
  if (props.isAiRemoveMode || props.showCropOverlay) return
  onMouseDown(e)
}

</script>

<template>
  <div class="preview-display">
    <div
      ref="containerRef"
      class="preview-image"
      :class="{ dragging: isDragging, 'draw-mode': isAiRemoveMode, 'crop-mode': showCropOverlay }"
      @wheel.prevent="onWheel"
      @mousedown="handleMouseDown"
    >
      <img
        ref="imgRef"
        :src="previewUrl ?? undefined"
        alt="原圖"
        :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoomLevel})` }"
        @load="handleImageLoad"
      />
      <canvas
        v-if="isAiRemoveMode"
        ref="maskCanvasRef"
        class="mask-canvas"
        @mousedown.prevent.stop="onCanvasMouseDown"
        @mousemove.prevent="onCanvasMouseMove"
        @mouseup="onCanvasMouseUp"
        @mouseleave="onCanvasMouseLeave"
        @wheel.prevent="onWheel"
      />
      <canvas
        v-else-if="showCropOverlay"
        ref="cropCanvasRef"
        class="mask-canvas crop-canvas"
        @mousedown.prevent.stop="onCropMouseDown"
        @mousemove.prevent="onCropMouseMove"
        @mouseup="onCropMouseUp"
        @mouseleave="onCropMouseLeave"
        @wheel.prevent="onWheel"
      />
    </div>

  </div>
</template>

<style lang="scss" scoped>
.preview-display {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.preview-image {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  overflow: hidden;
  cursor: grab;

  &.dragging  { cursor: grabbing; }
  &.draw-mode { cursor: crosshair; }
  &.crop-mode { cursor: crosshair; }

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    transform-origin: center center;
    user-select: none;
    pointer-events: none;
  }
}

.mask-canvas {
  position: absolute;
  cursor: none;
  z-index: 5;
  pointer-events: auto;

  &.crop-canvas { cursor: crosshair; }
}
</style>
