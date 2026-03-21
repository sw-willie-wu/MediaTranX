<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/logger'

const { t } = useI18n()
const log = createLogger('ComparisonSlider')

const props = defineProps<{
  originalUrl: string
  resultUrl: string
  resultMeta?: Record<string, unknown>
}>()

const sliderPosition = ref(50)
const isDraggingSlider = ref(false)
const containerRef = ref<HTMLElement | null>(null)

// 用 offscreen Image() 偵測原始結果圖的真實尺寸，避免 visible <img> onload 迴圈
const originalSize = ref<{ w: number; h: number } | null>(null)
const resultSize = ref<{ w: number; h: number } | null>(null)
const rawResultImg = ref<HTMLImageElement | null>(null)

const paddedResultUrl = ref<string | null>(null)
// 透過 fetch 取得的 blob URL，需在 unmount 時釋放
const resultBlobUrl = ref<string | null>(null)

function tryGeneratePadded() {
  if (!originalSize.value || !resultSize.value || !rawResultImg.value) return
  const ow = originalSize.value.w, oh = originalSize.value.h
  const rw = resultSize.value.w, rh = resultSize.value.h

  log.info('tryGeneratePadded', {
    original: { w: ow, h: oh },
    result: { w: rw, h: rh },
    meta: props.resultMeta,
  })

  // 沒有裁切資訊 → 不需要空間對位（超解析/濾鏡等用 object-fit: contain 即可對齊）
  const hasCropMeta = props.resultMeta?.crop_x != null
  if (!hasCropMeta) {
    log.info('no crop meta, skipping padded canvas')
    paddedResultUrl.value = null
    return
  }

  try {
    const canvas = document.createElement('canvas')
    canvas.width = ow
    canvas.height = oh
    const ctx = canvas.getContext('2d')!

    // 從 meta 取得裁切偏移量與裁切區域尺寸
    const rawCropX = props.resultMeta?.crop_x as number | undefined
    const rawCropY = props.resultMeta?.crop_y as number | undefined
    const sourceW = props.resultMeta?.source_width as number | undefined
    const sourceH = props.resultMeta?.source_height as number | undefined
    const cropW = props.resultMeta?.crop_width as number | undefined
    const cropH = props.resultMeta?.crop_height as number | undefined

    if (rawCropX != null && rawCropY != null && sourceW && sourceH) {
      // 裁切座標基於 source 尺寸（可能經過超解析等變換），需換算回原圖座標系
      const scaleX = ow / sourceW
      const scaleY = oh / sourceH
      const dx = Math.round(rawCropX * scaleX)
      const dy = Math.round(rawCropY * scaleY)
      // 用裁切區域的原始尺寸（不受後續超解析影響），fallback 到結果圖尺寸
      const dw = Math.round((cropW ?? rw) * scaleX)
      const dh = Math.round((cropH ?? rh) * scaleY)
      ctx.drawImage(rawResultImg.value, 0, 0, rw, rh, dx, dy, dw, dh)
    } else {
      // 沒有裁切資訊，置中
      const cx = Math.round((ow - rw) / 2)
      const cy = Math.round((oh - rh) / 2)
      ctx.drawImage(rawResultImg.value, cx, cy)
    }

    paddedResultUrl.value = canvas.toDataURL('image/png')
    log.info('padded canvas generated successfully')
  } catch (e) {
    log.warn('failed to generate padded canvas', e)
    paddedResultUrl.value = null
  }
}

function onOriginalLoad(e: Event) {
  const img = e.target as HTMLImageElement
  originalSize.value = { w: img.naturalWidth, h: img.naturalHeight }
  log.info('original loaded', { w: img.naturalWidth, h: img.naturalHeight })
  tryGeneratePadded()
}

// 用 fetch → blob URL 載入結果圖，避免 CORS tainted canvas 問題
// fetch 走 CORSMiddleware 正常回傳 CORS header；blob URL 為 same-origin 不會 taint canvas
function loadRawResult(url: string) {
  log.info('loadRawResult', { url })
  fetch(url)
    .then((res) => {
      if (!res.ok) throw new Error(`fetch failed: ${res.status}`)
      return res.blob()
    })
    .then((blob) => {
      // 釋放舊的 blob URL
      if (resultBlobUrl.value) URL.revokeObjectURL(resultBlobUrl.value)
      const blobUrl = URL.createObjectURL(blob)
      resultBlobUrl.value = blobUrl

      const img = new Image()
      img.onload = () => {
        resultSize.value = { w: img.naturalWidth, h: img.naturalHeight }
        rawResultImg.value = img
        log.info('result loaded via blob', { w: img.naturalWidth, h: img.naturalHeight })
        tryGeneratePadded()
      }
      img.src = blobUrl
    })
    .catch((e) => {
      log.warn('failed to fetch result image', e)
    })
}

// 初始載入 + URL 變化時重新載入
loadRawResult(props.resultUrl)

watch(() => props.resultUrl, (url) => {
  paddedResultUrl.value = null
  resultSize.value = null
  rawResultImg.value = null
  loadRawResult(url)
})

watch(() => props.originalUrl, () => {
  originalSize.value = null
  paddedResultUrl.value = null
})

// resultMeta 變更時重新生成 padded canvas（例如新操作完成後 meta 更新）
watch(() => props.resultMeta, () => {
  tryGeneratePadded()
}, { deep: true })

// Slider 實際使用的結果圖 URL
const effectiveResultUrl = computed(() => paddedResultUrl.value ?? props.resultUrl)

function startSliderDrag(e: MouseEvent | TouchEvent) {
  e.preventDefault()
  isDraggingSlider.value = true
  document.addEventListener('mousemove', onSliderDrag)
  document.addEventListener('mouseup', stopSliderDrag)
  document.addEventListener('touchmove', onSliderDrag)
  document.addEventListener('touchend', stopSliderDrag)
}

function onSliderDrag(e: MouseEvent | TouchEvent) {
  if (!isDraggingSlider.value || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
  sliderPosition.value = pct
}

function stopSliderDrag() {
  isDraggingSlider.value = false
  document.removeEventListener('mousemove', onSliderDrag)
  document.removeEventListener('mouseup', stopSliderDrag)
  document.removeEventListener('touchmove', onSliderDrag)
  document.removeEventListener('touchend', stopSliderDrag)
}

onBeforeUnmount(() => {
  stopSliderDrag()
  if (resultBlobUrl.value) URL.revokeObjectURL(resultBlobUrl.value)
})
</script>

<template>
  <div ref="containerRef" class="compare-slider-container">
    <img
      :src="originalUrl"
      :alt="$t('common.original')"
      class="compare-img compare-img-original"
      :style="{ clipPath: `inset(0 ${100 - sliderPosition}% 0 0)` }"
      @load="onOriginalLoad"
    />
    <img
      :src="effectiveResultUrl"
      :alt="$t('common.result')"
      class="compare-img compare-img-result"
      :style="{ clipPath: `inset(0 0 0 ${sliderPosition}%)` }"
    />
    <div
      class="slider-handle"
      :style="{ left: `${sliderPosition}%` }"
      @mousedown="startSliderDrag"
      @touchstart="startSliderDrag"
    >
      <div class="slider-line"></div>
      <div class="slider-grip">
        <i class="bi bi-grip-vertical"></i>
      </div>
    </div>
    <span class="compare-label compare-label-left">{{ $t('common.original') }}</span>
    <span class="compare-label compare-label-right">{{ $t('common.result') }}</span>
  </div>
</template>

<style lang="scss" scoped>
.compare-slider-container {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  user-select: none;
}

.compare-img {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.compare-img-original { z-index: 1; }
.compare-img-result   { z-index: 2; }

.slider-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 3;
  width: 4px;
  transform: translateX(-50%);
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
}

.slider-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
}

.slider-grip {
  position: relative;
  z-index: 4;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 50%;
  color: #333;
  font-size: 0.9rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.compare-label {
  position: absolute;
  bottom: 1rem;
  z-index: 5;
  padding: 0.25rem 0.75rem;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 6px;
  color: white;
  font-size: 0.75rem;
  pointer-events: none;

  &-left  { left: 1rem; }
  &-right { right: 1rem; }
}
</style>
