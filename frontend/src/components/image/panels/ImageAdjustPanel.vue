<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import type { FilterPreview } from './filterTypes'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'preview-change': [preview: FilterPreview]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const brightness = ref(100)
const contrast   = ref(100)
const saturation = ref(100)
const hue        = ref(0)
const sharpness  = ref(100)
const warmth     = ref(0)

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

const preview = computed<FilterPreview>(() => ({
  brightness: brightness.value / 100,
  contrast:   contrast.value / 100,
  saturation: saturation.value / 100,
  hue:        hue.value,
  sharpness:  sharpness.value / 100,
  warmth:     warmth.value / 100,
  grayscale:  0,
  sepia:      0,
  invert:     0,
  blur:       0,
  vignette:   0,
}))

watch(preview, (val) => emit('preview-change', val), { immediate: true })

export interface AdjustState {
  brightness: number
  contrast:   number
  saturation: number
  hue:        number
  sharpness:  number
  warmth:     number
}

function getState(): AdjustState {
  return {
    brightness: brightness.value,
    contrast:   contrast.value,
    saturation: saturation.value,
    hue:        hue.value,
    sharpness:  sharpness.value,
    warmth:     warmth.value,
  }
}

function setState(s: AdjustState) {
  brightness.value = s.brightness
  contrast.value   = s.contrast
  saturation.value = s.saturation
  hue.value        = s.hue
  sharpness.value  = s.sharpness
  warmth.value     = s.warmth
}

function reset() {
  brightness.value = 100
  contrast.value   = 100
  saturation.value = 100
  hue.value        = 0
  sharpness.value  = 100
  warmth.value     = 0
}

function getParams(): Record<string, unknown> {
  return {
    brightness: brightness.value / 100,
    contrast:   contrast.value / 100,
    saturation: saturation.value / 100,
    hue:        hue.value,
    sharpness:  sharpness.value / 100,
    warmth:     warmth.value / 100,
  }
}

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/image/filter',
    { file_id: props.fileId, ...getParams() },
    '圖片調整',
    'image.filter',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, getState, setState, getParams, getPreview: () => preview.value })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-sliders me-2"></i>調整設定</h6>
    <p class="form-hint">調整影像基本色調參數，所有變更即時反映於預覽。</p>

    <div class="form-group">
      <label>亮度 <span class="param-value">{{ brightness }}%</span></label>
      <AppRange v-model="brightness" :min="10" :max="300" :step="5" />
    </div>

    <div class="form-group">
      <label>對比度 <span class="param-value">{{ contrast }}%</span></label>
      <AppRange v-model="contrast" :min="10" :max="300" :step="5" />
    </div>

    <div class="form-group">
      <label>飽和度 <span class="param-value">{{ saturation }}%</span></label>
      <AppRange v-model="saturation" :min="0" :max="300" :step="5" />
    </div>

    <div class="form-group">
      <label>色相 <span class="param-value">{{ hue > 0 ? '+' : '' }}{{ hue }}°</span></label>
      <AppRange v-model="hue" :min="-180" :max="180" :step="5" />
    </div>

    <div class="form-group">
      <label>銳利度 <span class="param-value">{{ sharpness }}%</span></label>
      <AppRange v-model="sharpness" :min="0" :max="300" :step="5" />
    </div>

    <div class="form-group">
      <label>
        色溫
        <span class="param-value">
          {{ warmth > 0 ? `暖 +${warmth}` : warmth < 0 ? `冷 ${warmth}` : '0' }}
        </span>
      </label>
      <AppRange v-model="warmth" :min="-100" :max="100" :step="5" />
    </div>

    <div class="form-group">
      <button class="btn-secondary" @click="reset">
        <i class="bi bi-arrow-counterclockwise"></i>重設調整
      </button>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
