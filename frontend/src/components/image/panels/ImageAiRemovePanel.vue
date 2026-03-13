<script setup lang="ts">
import { computed } from 'vue'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  brushSize: number
  getMask: () => string | null
  hasMask: () => boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'update:brushSize': [value: number]
  clearMask: []
}>()

const toast = useToast()
const { submitTask, isProcessing } = useSubmitTask()

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  if (!props.hasMask()) {
    toast.show('請先在圖片上塗抹要移除的區域', { type: 'info', icon: 'bi-info-circle' })
    return
  }
  const maskData = props.getMask()
  if (!maskData) return

  const taskId = await submitTask(
    '/image/remove-object',
    { file_id: props.fileId, mask_data: maskData },
    'AI 物件移除',
    'image.remove_object',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-magic me-2"></i>物件移除設定
    </h6>

    <p class="form-hint">在圖片上塗抹要移除的物件，AI 將自動填補背景</p>

    <div class="form-group">
      <label>
        筆刷大小
        <span class="param-value">{{ brushSize }}</span>
      </label>
      <AppRange
        :model-value="brushSize"
        :min="1"
        :max="80"
        :step="1"
        @update:model-value="emit('update:brushSize', $event)"
      />
      <div class="range-ticks">
        <span>細</span><span>粗</span>
      </div>
    </div>

    <div class="form-group">
      <button class="btn-secondary" :disabled="isDisabled" @click="emit('clearMask')">
        <i class="bi bi-trash"></i>清除塗抹
      </button>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
