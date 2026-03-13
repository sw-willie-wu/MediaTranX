<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  originalUrl: string
  resultUrl: string
}>()

const sliderPosition = ref(50)
const isDraggingSlider = ref(false)
const containerRef = ref<HTMLElement | null>(null)

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
</script>

<template>
  <div ref="containerRef" class="compare-slider-container">
    <img :src="originalUrl" alt="原圖" class="compare-img compare-img-original" />
    <img
      :src="resultUrl"
      alt="成果"
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
    <span class="compare-label compare-label-left">原圖</span>
    <span class="compare-label compare-label-right">成果</span>
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
  border-radius: 4px;
  color: white;
  font-size: 0.75rem;
  pointer-events: none;

  &-left  { left: 1rem; }
  &-right { right: 1rem; }
}
</style>
