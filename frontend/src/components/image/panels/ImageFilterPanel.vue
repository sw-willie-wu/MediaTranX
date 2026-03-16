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

const grayscale = ref(0)
const sepia     = ref(0)
const invert    = ref(0)
const blur      = ref(0)
const vignette  = ref(0)

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

function getParams(): Record<string, unknown> {
  return {
    grayscale: grayscale.value / 100,
    sepia:     sepia.value / 100,
    invert:    invert.value / 100,
    blur:      blur.value,
    vignette:  vignette.value / 100,
  }
}

const preview = computed<FilterPreview>(() => ({
  brightness: 1,
  contrast:   1,
  saturation: 1,
  hue:        0,
  sharpness:  1,
  warmth:     0,
  grayscale:  grayscale.value / 100,
  sepia:      sepia.value / 100,
  invert:     invert.value / 100,
  blur:       blur.value,
  vignette:   vignette.value / 100,
}))

watch(preview, (val) => emit('preview-change', val), { immediate: true })

export interface FilterState {
  grayscale: number
  sepia:     number
  invert:    number
  blur:      number
  vignette:  number
}

function getState(): FilterState {
  return {
    grayscale: grayscale.value,
    sepia:     sepia.value,
    invert:    invert.value,
    blur:      blur.value,
    vignette:  vignette.value,
  }
}

function setState(s: FilterState) {
  grayscale.value = s.grayscale
  sepia.value     = s.sepia
  invert.value    = s.invert
  blur.value      = s.blur
  vignette.value  = s.vignette
}

function reset() {
  grayscale.value = 0
  sepia.value     = 0
  invert.value    = 0
  blur.value      = 0
  vignette.value  = 0
}

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/image/filter',
    {
      file_id: props.fileId,
      ...getParams(),
    },
    '圖片濾鏡',
    'image.filter',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, getParams, getState, setState })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-palette-fill me-2"></i>濾鏡設定</h6>
    <p class="form-hint">套用視覺風格效果，所有變更即時反映於預覽。</p>

    <div class="form-group">
      <label>灰階 <span class="param-value">{{ grayscale }}%</span></label>
      <AppRange v-model="grayscale" :min="0" :max="100" :step="5" />
    </div>

    <div class="form-group">
      <label>復古 <span class="param-value">{{ sepia }}%</span></label>
      <AppRange v-model="sepia" :min="0" :max="100" :step="5" />
    </div>

    <div class="form-group">
      <label>負片 <span class="param-value">{{ invert }}%</span></label>
      <AppRange v-model="invert" :min="0" :max="100" :step="5" />
    </div>

    <div class="form-group">
      <label>模糊 <span class="param-value">{{ blur }}px</span></label>
      <AppRange v-model="blur" :min="0" :max="20" :step="1" />
    </div>

    <div class="form-group">
      <label>暈影 <span class="param-value">{{ vignette }}%</span></label>
      <AppRange v-model="vignette" :min="0" :max="100" :step="5" />
    </div>

    <div class="form-group">
      <button class="btn-secondary" @click="reset">
        <i class="bi bi-arrow-counterclockwise"></i>重設濾鏡
      </button>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

