<script setup lang="ts">
import { ref, computed, toRef, watch, nextTick } from 'vue'
import { useImageZoom } from '@/composables/useImageZoom'
import { useCanvasMask } from '@/composables/useCanvasMask'
import { useCropRect } from '@/composables/useCropRect'
import type { ImageInfo } from '@/composables/useImageWorkspace'
import type { FilterPreview } from '@/components/image/panels/filterTypes'

const props = defineProps<{
  previewUrl: string | null
  imageInfo: ImageInfo | null
  isAiRemoveMode: boolean
  showCropOverlay: boolean
  cropAspectRatio?: string
  filterPreview?: FilterPreview | null
  brushSize?: number
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

// 同步外部 brushSize prop 到 composable
watch(() => props.brushSize, (v) => { if (v !== undefined) brushSize.value = v })

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

// 縮放/拖曳時重新定位 canvas（遮罩與裁切）
watch([zoomLevel, panX, panY], () => {
  nextTick(() => {
    if (props.isAiRemoveMode) syncToImage()
    if (props.showCropOverlay) repositionCropCanvas()
  })
})

// 裁切矩形變動時通知父層
watch(cropRect, (rect) => {
  emit('crop-rect-change', rect ?? null)
})

// ── CSS + SVG Filter preview ─────────────────────────────────────────────────

// SVG unsharp-mask kernel (feConvolveMatrix 3×3)
// strength = (sharpness - 1) * 0.3  →  center = 1 + 8s, sides = -s
const svgSharpKernel = computed(() => {
  const sharpness = props.filterPreview?.sharpness ?? 1.0
  const s = Math.max(0, (sharpness - 1.0) * 0.3)
  const center = +(1 + 8 * s).toFixed(4)
  const side   = +(-s).toFixed(4)
  return `${side} ${side} ${side} ${side} ${center} ${side} ${side} ${side} ${side}`
})

// SVG warmth matrix (feColorMatrix): shift R and B channels
// warmth range: -1 (cold) ~ 1 (warm)
const svgWarmMatrix = computed(() => {
  const w = props.filterPreview?.warmth ?? 0
  const rOff = +(w * 0.118).toFixed(4)   // warm: +R, cool: -R
  const bOff = +(-w * 0.078).toFixed(4)  // warm: -B, cool: +B
  return `1 0 0 0 ${rOff}  0 1 0 0 0  0 0 1 0 ${bOff}  0 0 0 1 0`
})


const needsSvgFilter = computed(() => {
  const f = props.filterPreview
  if (!f) return false
  return (f.sharpness ?? 1.0) !== 1.0 || (f.warmth ?? 0) !== 0
})

const cssFilter = computed(() => {
  const f = props.filterPreview
  if (!f) return ''
  const parts: string[] = []
  if (f.brightness !== 1)  parts.push(`brightness(${f.brightness})`)
  if (f.contrast !== 1)    parts.push(`contrast(${f.contrast})`)
  if (f.saturation !== 1)  parts.push(`saturate(${f.saturation})`)
  if (f.hue !== 0)         parts.push(`hue-rotate(${f.hue}deg)`)
  if (f.grayscale > 0)     parts.push(`grayscale(${f.grayscale})`)
  if (f.sepia > 0)         parts.push(`sepia(${f.sepia})`)
  if (f.invert > 0)        parts.push(`invert(${f.invert})`)
  if (f.blur > 0)          parts.push(`blur(${f.blur}px)`)
  // sharpness < 1: soften via CSS blur
  const sharpness = f.sharpness ?? 1.0
  if (sharpness < 1.0) parts.push(`blur(${((1.0 - sharpness) * 2).toFixed(2)}px)`)
  // SVG filter handles sharpness > 1 and warmth
  if (needsSvgFilter.value) parts.push('url(#preview-adj-filter)')
  return parts.join(' ')
})

const vignetteStyle = computed(() => {
  const f = props.filterPreview
  if (!f || f.vignette <= 0) return null
  const v = f.vignette
  const spread = Math.round(100 - v * 65)
  const opacity = (v * 0.85).toFixed(2)
  return { background: `radial-gradient(ellipse at center, transparent ${spread}%, rgba(0,0,0,${opacity}) 100%)` }
})

defineExpose({
  clearMask, exportMask, hasMask, syncToImage,
  cropRect, clearCropRect, syncCropCanvas,
  isAiRemoveActive: () => props.isAiRemoveMode, zoomPercent,
  getZoomState: () => ({ zoomLevel: zoomLevel.value, panX: panX.value, panY: panY.value }),
  setZoomState: (s: { zoomLevel: number; panX: number; panY: number }) => {
    zoomLevel.value = s.zoomLevel
    panX.value = s.panX
    panY.value = s.panY
  },
  resetZoom: reset,
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
    <!-- Hidden SVG: sharpness (feConvolveMatrix) + warmth (feColorMatrix) -->
    <svg v-if="filterPreview" width="0" height="0" style="position:absolute;overflow:hidden">
      <defs>
        <filter id="preview-adj-filter" color-interpolation-filters="sRGB">
          <feConvolveMatrix
            order="3"
            :kernelMatrix="svgSharpKernel"
            divisor="1"
            result="sharp"
          />
          <feColorMatrix
            type="matrix"
            :values="svgWarmMatrix"
            in="sharp"
          />
        </filter>
      </defs>
    </svg>
    <div
      ref="containerRef"
      class="preview-image"
      :class="{ dragging: isDragging, 'draw-mode': isAiRemoveMode, 'crop-mode': showCropOverlay }"
      @wheel.prevent="onWheel"
      @mousedown="handleMouseDown"
    >
      <!-- image-transform 包住圖片與暈影，讓 inset:0 的 overlay 只覆蓋圖片 -->
      <div
        class="image-transform"
        :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoomLevel})` }"
      >
        <img
          ref="imgRef"
          :src="previewUrl ?? undefined"
          alt="原圖"
          :style="{ filter: cssFilter || undefined }"
          @load="handleImageLoad"
        />
        <div v-if="vignetteStyle" class="vignette-overlay" :style="vignetteStyle" />
      </div>
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
  &.crop-mode { cursor: crosshair; overflow: visible; }

}

.image-transform {
  position: relative;       // vignette overlay 的 inset:0 基準
  display: inline-flex;     // 自動縮為圖片實際尺寸
  max-width: 100%;
  max-height: 100%;
  transform-origin: center center;
  line-height: 0;           // 消除 inline-flex 底部間距

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    user-select: none;
    pointer-events: none;
    display: block;
  }
}


.mask-canvas {
  position: absolute;
  cursor: none;
  z-index: 5;
  pointer-events: auto;

  &.crop-canvas { cursor: crosshair; }
}

.vignette-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
}
</style>
