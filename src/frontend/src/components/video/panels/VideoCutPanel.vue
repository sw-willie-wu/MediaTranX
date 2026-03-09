<script setup lang="ts">
import { computed } from 'vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'
import AppToggle from '@/components/common/AppToggle.vue'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  startTime: string
  endTime: string
  streamCopy: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'update:startTime': [v: string]
  'update:endTime': [v: string]
  'update:streamCopy': [v: boolean]
}>()

const toast = useToast()
const { submitTask, isProcessing } = useSubmitTask()

function parseTimeToSeconds(time: string): number {
  const parts = time.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return Number(time) || 0
}

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return

  const startSeconds = parseTimeToSeconds(props.startTime)
  const endSeconds = parseTimeToSeconds(props.endTime)

  if (endSeconds <= startSeconds) {
    toast.show('結束時間必須大於開始時間', { type: 'error', icon: 'bi-x-circle' })
    return
  }

  const taskId = await submitTask(
    '/video/cut',
    {
      file_id: props.fileId,
      start_time: startSeconds,
      end_time: endSeconds,
      stream_copy: props.streamCopy,
    },
    '剪輯',
    'video.cut',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-scissors me-2"></i>剪輯</h6>

    <div class="form-group">
      <label>開始時間 (HH:MM:SS)</label>
      <input
        :value="startTime"
        type="text"
        class="form-input"
        placeholder="00:00:00"
        @input="emit('update:startTime', ($event.target as HTMLInputElement).value)"
      />
    </div>

    <div class="form-group">
      <label>結束時間 (HH:MM:SS)</label>
      <input
        :value="endTime"
        type="text"
        class="form-input"
        placeholder="00:00:00"
        @input="emit('update:endTime', ($event.target as HTMLInputElement).value)"
      />
    </div>

    <div class="form-group">
      <AppToggle
        :modelValue="streamCopy"
        @update:modelValue="emit('update:streamCopy', $event)"
      >快速模式（不重新編碼）</AppToggle>
      <small class="form-hint">關閉可獲得精確剪輯點，但速度較慢</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
