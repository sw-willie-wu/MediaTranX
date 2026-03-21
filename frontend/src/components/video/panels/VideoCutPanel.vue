<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'
import AppToggle from '@/components/common/AppToggle.vue'

const { t } = useI18n()

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
    toast.show(t('video.cut.time_error'), { type: 'error', icon: 'bi-x-circle' })
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
    t('video.cut.task_label'),
    'video.cut',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-scissors me-2"></i>{{ $t('video.cut.title') }}</h6>
    <p class="form-hint">{{ $t('video.cut.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.cut.start_time') }}</label>
      <input
        :value="startTime"
        type="text"
        class="form-input"
        placeholder="00:00:00"
        @input="emit('update:startTime', ($event.target as HTMLInputElement).value)"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('video.cut.end_time') }}</label>
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
      >{{ $t('video.cut.fast_mode') }}</AppToggle>
      <small class="form-hint">{{ $t('video.cut.fast_mode_hint') }}</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
