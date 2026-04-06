<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'

const { t } = useI18n()

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  mediaInfo: { fps?: number } | null
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const model = ref('v4.26')
const mode = ref('2x')
const targetFps = ref(60)
const outputFormat = ref('mp4')
const videoCodec = ref('h264')
const showAdvanced = ref(false)

const modelOptions = computed(() => [
  { value: 'v4.26', label: 'RIFE v4.26' },
])

const modeOptions = computed(() => [
  { value: '2x', label: t('video.interpolate.mode_2x') },
  { value: '4x', label: t('video.interpolate.mode_4x') },
  { value: 'custom', label: t('video.interpolate.mode_custom') },
])

const formatOptions = computed(() => [
  { value: 'mp4', label: 'MP4' },
  { value: 'mkv', label: 'MKV' },
  { value: 'webm', label: 'WebM' },
  { value: 'mov', label: 'MOV' },
])

const codecOptions = computed(() => [
  { value: 'h264', label: 'H.264' },
  { value: 'h265', label: 'H.265 (HEVC)' },
  { value: 'vp9', label: 'VP9' },
  { value: 'av1', label: 'AV1' },
])

const sourceFps = computed(() => props.mediaInfo?.fps || 0)

const outputFps = computed(() => {
  if (mode.value === 'custom') return targetFps.value
  if (mode.value === '4x') return sourceFps.value * 4
  return sourceFps.value * 2
})

const fpsWarning = computed(() => {
  if (mode.value === 'custom' && targetFps.value <= sourceFps.value) return true
  return false
})

const isDisabled = computed(() => !props.fileId || isProcessing.value || fpsWarning.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId || fpsWarning.value) return

  const taskId = await submitTask(
    '/video/interpolate',
    {
      file_id: props.fileId,
      model: model.value,
      mode: mode.value,
      target_fps: mode.value === 'custom' ? targetFps.value : undefined,
      output_format: outputFormat.value,
      video_codec: videoCodec.value,
    },
    t('video.interpolate.task_label'),
    'video.interpolate',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-speedometer2 me-2"></i>{{ $t('video.interpolate.title') }}</h6>
    <p class="form-hint">{{ $t('video.interpolate.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.interpolate.model') }}</label>
      <AppSelect v-model="model" :options="modelOptions" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.interpolate.mode') }}</label>
      <AppSelect v-model="mode" :options="modeOptions" />
    </div>

    <div v-if="mode === 'custom'" class="form-group">
      <label>{{ $t('video.interpolate.target_fps') }}: {{ targetFps }}</label>
      <AppRange v-model="targetFps" :min="Math.ceil(sourceFps) + 1 || 2" :max="240" :step="1" />
      <small v-if="fpsWarning" class="form-hint text-danger">{{ $t('video.interpolate.fps_warning') }}</small>
    </div>

    <div v-if="sourceFps > 0" class="form-group fps-info">
      <span>{{ $t('video.interpolate.current_fps') }}: <strong>{{ sourceFps.toFixed(1) }}</strong></span>
      <span class="fps-arrow">→</span>
      <span>{{ $t('video.interpolate.output_fps') }}: <strong>{{ outputFps.toFixed(1) }}</strong></span>
    </div>

    <div class="advanced-toggle" @click="showAdvanced = !showAdvanced">
      <i class="bi" :class="showAdvanced ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
      <span>{{ $t('common.advanced_options') }}</span>
    </div>

    <template v-if="showAdvanced">
      <div class="form-group">
        <label>{{ $t('video.interpolate.output_format') }}</label>
        <AppSelect v-model="outputFormat" :options="formatOptions" />
      </div>

      <div class="form-group">
        <label>{{ $t('video.interpolate.video_codec') }}</label>
        <AppSelect v-model="videoCodec" :options="codecOptions" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.fps-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 0.875rem;
}
.fps-arrow {
  color: var(--color-primary);
  font-weight: bold;
}
.text-danger {
  color: var(--color-danger);
}
.advanced-toggle {
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin: 0.5rem 0;
  user-select: none;
}
.advanced-toggle:hover {
  color: var(--text-primary);
}
</style>
