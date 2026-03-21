<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  duration?: number
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const startTime = ref('00:00:00')
const endTime = ref('00:00:00')

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/audio/cut',
    { file_id: props.fileId, start_time: startTime.value, end_time: endTime.value },
    t('audio.cut.task_label'),
    'audio.cut',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-scissors me-2"></i>{{ $t('audio.cut.title') }}</h6>
    <p class="form-hint">{{ $t('audio.cut.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.cut.start_time') }}</label>
      <input type="text" class="form-input" v-model="startTime" placeholder="00:00:00" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.cut.end_time') }}</label>
      <input type="text" class="form-input" v-model="endTime" placeholder="00:00:00" />
      <small v-if="duration" class="form-hint">
        {{ $t('audio.cut.duration') }} {{ Math.floor(duration / 60) }}:{{ String(Math.floor(duration % 60)).padStart(2, '0') }}
      </small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

