<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'

const { t } = useI18n()

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  startTime: string
  endTime: string
  streamCopy: boolean
  isMultiSelect?: boolean
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

// ───────────────────────── Agent integration ─────────────────────────
const agentSchema = {
  panelId: 'video.cut',
  fields: [
    { name: 'start_time',  type: 'string' as const },
    { name: 'end_time',    type: 'string' as const },
    { name: 'stream_copy', type: 'bool'   as const },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.cut.execute' },
}

useAgentPanelHost('video.cut', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    start_time:  props.startTime,
    end_time:    props.endTime,
    stream_copy: props.streamCopy,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'start_time':  emit('update:startTime', String(value));   return String(value)
      case 'end_time':    emit('update:endTime',   String(value));   return String(value)
      case 'stream_copy': emit('update:streamCopy', Boolean(value)); return Boolean(value)
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {}, // no enum/AppSelect
  execute: async () => {
    await execute()
    return {}
  },
})
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

    <SettingsCollapsible storage-key="video_cut_advanced">
      <div class="form-group">
        <AppToggle
          :modelValue="streamCopy"
          @update:modelValue="emit('update:streamCopy', $event)"
        >{{ $t('video.cut.fast_mode') }}</AppToggle>
        <small class="form-hint">{{ $t('video.cut.fast_mode_hint') }}</small>
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
