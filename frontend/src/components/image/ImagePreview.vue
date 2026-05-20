<script setup lang="ts">
import { ref, computed, toRef, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useImageZoom } from '@/composables/useImageZoom'
import { useCanvasMask, type MaskToolMode } from '@/composables/useCanvasMask'
import { useCropRect } from '@/composables/useCropRect'
import { useWebGLFilter } from '@/composables/useWebGLFilter'
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
  toolMode?: MaskToolMode
}>()

const emit = defineEmits<{
  'canvas-ready': [exportFn: () => ImageData | null, hasMask: Readonly<{ value: boolean }>, brushSize: Readonly<{ value: number }>, clearFn: () => void]
  'brush-size-change': [size: number]
  'crop-rect-change': [rect: { x: number; y: number; w: number; h: number } | null]
}>()

// ── Refs ────────────────────────────────────────────────────────────────
const imgRef = ref<HTMLImageElement | null>(null)
const containerRef = ref<HTMLElement | null>(null)
const glCanvasRef = ref<HTMLCanvasElement | null>(null)

// ── Zoom/Pan ─────────────────────────────────────────────────────────────
const { zoomLevel, panX, panY, isDragging, zoomPercent, reset, onWheel, onImageLoad, onMouseDown } =
  useImageZoom(imgRef, containerRef)

// ── Canvas Mask ──────────────────────────────────────────────────────────
const {
  canvasRef: maskCanvasRef,
  brushSize,
  toolMode,
  syncToImage,
  onMouseDown: onCanvasMouseDown,
  onMouseMove: onCanvasMouseMove,
  onMouseUp: onCanvasMouseUp,
  onMouseLeave: onCanvasMouseLeave,
  onDblClick: onCanvasDblClick,
  onContextMenu: onCanvasContextMenu,
  cancelShape,
  clearMask,
  hasMask,
  exportMask,
} = useCanvasMask(imgRef, containerRef)

// 同步外部 props 到 composable
watch(() => props.brushSize, (v) => { if (v !== undefined) brushSize.value = v })
watch(() => props.toolMode, (v) => { if (v !== undefined) toolMode.value = v })

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

// ── WebGL Filter preview ─────────────────────────────────────────────────
const { isReady: glReady, isSupported: glSupported, loadImage: glLoadImage, updateFilters: glUpdateFilters, dispose: glDispose } =
  useWebGLFilter(glCanvasRef)

const webglActive = computed(() => !!props.filterPreview && glSupported.value)

/** Detect transparent images (checkerboard background helps visualize alpha). */
const hasAlpha = computed(() => {
  const mode = props.imageInfo?.mode?.toUpperCase() ?? ''
  if (mode.includes('A') || mode === 'LA') return true // RGBA / LA / PA
  const ext = props.previewUrl?.split('?')[0].split('.').pop()?.toLowerCase() ?? ''
  return ['png', 'webp', 'avif', 'gif', 'tiff', 'tif'].includes(ext)
})

/** Natural aspect ratio — used to constrain the checkerboard wrapper to
 *  the displayed image size (object-fit: contain can letterbox the img box
 *  if it's stretched, but aspect-ratio on the wrapper keeps box = image box). */
const imgAspect = ref<string | null>(null)
function updateImgAspect() {
  const img = imgRef.value
  if (img && img.naturalWidth && img.naturalHeight) {
    imgAspect.value = `${img.naturalWidth} / ${img.naturalHeight}`
  }
}

async function tryLoadGL(url: string): Promise<boolean> {
  try {
    await glLoadImage(url)
    return true
  } catch (e) {
    console.warn('[ImagePreview] WebGL load failed, falling back to native img:', e)
    return false
  }
}

// When WebGL canvas mounts (v-if), load image and render
watch(glCanvasRef, async (canvas) => {
  if (canvas && props.previewUrl && props.filterPreview) {
    if (await tryLoadGL(props.previewUrl) && props.filterPreview) {
      glUpdateFilters(props.filterPreview)
    }
  }
})

// Load image into WebGL texture when previewUrl changes while filter is active
watch(() => props.previewUrl, async (url) => {
  // Refresh aspect even if browser cache hit skips the <img> @load event
  if (imgRef.value?.complete) updateImgAspect()
  if (url && props.filterPreview && glCanvasRef.value) {
    if (await tryLoadGL(url) && props.filterPreview) {
      glUpdateFilters(props.filterPreview)
    }
  }
})

// When filterPreview changes, update WebGL uniforms and re-render
watch(() => props.filterPreview, async (fp) => {
  if (fp && glCanvasRef.value) {
    if (!glReady.value && props.previewUrl) {
      await tryLoadGL(props.previewUrl)
    }
    if (glReady.value) glUpdateFilters(fp)
  }
}, { deep: true })

// CSS fallback for when WebGL is not supported
const cssFilter = computed(() => {
  const f = props.filterPreview
  if (!f || glSupported.value) return ''
  const parts: string[] = []
  if (f.brightness !== 1)  parts.push(`brightness(${f.brightness})`)
  if (f.contrast !== 1)    parts.push(`contrast(${f.contrast})`)
  if (f.saturation !== 1)  parts.push(`saturate(${f.saturation})`)
  if (f.hue !== 0)         parts.push(`hue-rotate(${f.hue}deg)`)
  if (f.grayscale > 0)     parts.push(`grayscale(${f.grayscale})`)
  if (f.sepia > 0)         parts.push(`sepia(${f.sepia})`)
  if (f.invert > 0)        parts.push(`invert(${f.invert})`)
  if (f.blur > 0)          parts.push(`blur(${f.blur}px)`)
  return parts.join(' ')
})

const vignetteStyle = computed(() => {
  const f = props.filterPreview
  if (!f || f.vignette <= 0 || glSupported.value) return null
  const v = f.vignette
  const spread = Math.round(100 - v * 65)
  const opacity = (v * 0.85).toFixed(2)
  return { background: `radial-gradient(ellipse at center, transparent ${spread}%, rgba(0,0,0,${opacity}) 100%)` }
})

// ── Space 鍵臨時平移（PS 風格）─────────────────────────────────────
const isSpaceHeld = ref(false)

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.isAiRemoveMode) cancelShape()
  if (e.code === 'Space' && !e.repeat && (props.isAiRemoveMode || props.showCropOverlay)) {
    e.preventDefault()
    isSpaceHeld.value = true
  }
}
function handleKeyUp(e: KeyboardEvent) {
  if (e.code === 'Space') isSpaceHeld.value = false
}
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
  glDispose()
})

defineExpose({
  clearMask, exportMask, hasMask, syncToImage, cancelShape,
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
  updateImgAspect()
  if (props.isAiRemoveMode) syncToImage()
  if (props.showCropOverlay) syncCropCanvas()
}

function handleMouseDown(e: MouseEvent) {
  if (props.isAiRemoveMode || props.showCropOverlay) return
  onMouseDown(e)
}

// Canvas 事件代理：Space 按住時轉發給 zoom/pan
function handleCanvasMouseDown(e: MouseEvent) {
  if (isSpaceHeld.value) { onMouseDown(e); return }
  onCanvasMouseDown(e)
}
function handleCanvasMouseMove(e: MouseEvent) {
  if (isSpaceHeld.value) return  // pan 由 document mousemove 處理
  onCanvasMouseMove(e)
}
function handleCanvasMouseUp(e: MouseEvent) {
  if (isSpaceHeld.value) return  // pan 由 document mouseup 處理
  onCanvasMouseUp()
}

// Crop canvas 事件代理：Space 按住時轉發給 zoom/pan
function handleCropMouseDown(e: MouseEvent) {
  if (isSpaceHeld.value) { onMouseDown(e); return }
  onCropMouseDown(e)
}
function handleCropMouseMove(e: MouseEvent) {
  if (isSpaceHeld.value) return
  onCropMouseMove(e)
}
function handleCropMouseUp(e: MouseEvent) {
  if (isSpaceHeld.value) return
  onCropMouseUp()
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
      <!-- image-transform 包住圖片與暈影，讓 inset:0 的 overlay 只覆蓋圖片 -->
      <div
        class="image-transform"
        :class="{ 'has-alpha': showCropOverlay && hasAlpha }"
        :style="{
          transform: `translate(${panX}px, ${panY}px) scale(${zoomLevel})`,
          aspectRatio: showCropOverlay && hasAlpha ? imgAspect ?? undefined : undefined,
        }"
      >
        <img
          ref="imgRef"
          :src="previewUrl ?? undefined"
          alt="原圖"
          :style="{ filter: cssFilter || undefined, opacity: webglActive && glReady ? 0 : 1 }"
          @load="handleImageLoad"
        />
        <canvas
          v-if="webglActive"
          ref="glCanvasRef"
          class="webgl-canvas"
        />
        <div v-if="vignetteStyle" class="vignette-overlay" :style="vignetteStyle" />
      </div>
      <canvas
        v-if="isAiRemoveMode"
        ref="maskCanvasRef"
        class="mask-canvas"
        :class="{ 'space-pan': isSpaceHeld }"
        @mousedown.prevent.stop="handleCanvasMouseDown"
        @mousemove.prevent="handleCanvasMouseMove"
        @mouseup="handleCanvasMouseUp"
        @mouseleave="onCanvasMouseLeave"
        @dblclick.prevent.stop="onCanvasDblClick"
        @contextmenu.prevent.stop="onCanvasContextMenu"
        @wheel.prevent="onWheel"
      />
      <canvas
        v-else-if="showCropOverlay"
        ref="cropCanvasRef"
        class="mask-canvas crop-canvas"
        :class="{ 'space-pan': isSpaceHeld }"
        @mousedown.prevent.stop="handleCropMouseDown"
        @mousemove.prevent="handleCropMouseMove"
        @mouseup="handleCropMouseUp"
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

}

.image-transform {
  position: relative;       // vignette overlay 的 inset:0 基準
  display: inline-flex;     // 自動縮為圖片實際尺寸
  max-width: 100%;
  max-height: 100%;
  transform-origin: center center;
  line-height: 0;           // 消除 inline-flex 底部間距

  // 透明 PNG 的棋盤背景：透過 aspect-ratio 把 .image-transform 約束成
  // 圖片自身的比例，所以它的 box = 顯示中的圖片區域，背景剛好覆蓋圖片
  &.has-alpha {
    background-color: var(--checkerboard-bg);
    background-image:
      linear-gradient(45deg, var(--checkerboard-square) 25%, transparent 25%),
      linear-gradient(-45deg, var(--checkerboard-square) 25%, transparent 25%),
      linear-gradient(45deg, transparent 75%, var(--checkerboard-square) 75%),
      linear-gradient(-45deg, transparent 75%, var(--checkerboard-square) 75%);
    background-size: 16px 16px;
    background-position: 0 0, 0 8px, 8px -8px, 8px 0;
  }

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
  &.space-pan   { cursor: grab; }
}

.webgl-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
  pointer-events: none;
  z-index: 1;
}

.vignette-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
}

</style>
