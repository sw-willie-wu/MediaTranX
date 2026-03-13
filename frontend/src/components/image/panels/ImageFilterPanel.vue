<script setup lang="ts">
import { ref, computed } from 'vue'
import AppRange from '@/components/common/AppRange.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const brightness = ref(100)
const contrast = ref(100)
const saturation = ref(100)
const sharpness = ref(100)
const grayscale = ref(false)

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

function reset() {
  brightness.value = 100
  contrast.value = 100
  saturation.value = 100
  sharpness.value = 100
  grayscale.value = false
}

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/image/filter',
    {
      file_id: props.fileId,
      brightness: brightness.value / 100,
      contrast: contrast.value / 100,
      saturation: saturation.value / 100,
      sharpness: sharpness.value / 100,
      grayscale: grayscale.value,
    },
    '圖片濾鏡',
    'image.filter',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-palette-fill me-2"></i>濾鏡設定</h6>
    <p class="form-hint">調整亮度、對比度、飽和度與銳利度，套用色調或預設濾鏡。</p>

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
      <label>銳利度 <span class="param-value">{{ sharpness }}%</span></label>
      <AppRange v-model="sharpness" :min="0" :max="300" :step="5" />
    </div>

    <div class="form-group">
      <AppToggle v-model="grayscale">灰階</AppToggle>
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
