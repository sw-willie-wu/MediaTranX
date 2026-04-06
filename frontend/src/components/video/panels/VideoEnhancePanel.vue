<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'
import AppSelect from '@/components/common/AppSelect.vue'

const { t } = useI18n()

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  mediaInfo: { width?: number; height?: number } | null
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const variant = ref('x4plus')
const outputFormat = ref('mp4')
const videoCodec = ref('h264')
const showAdvanced = ref(false)

const variantOptions = computed(() => [
  { value: 'x2plus', label: 'Real-ESRGAN x2' },
  { value: 'x4plus', label: 'Real-ESRGAN x4' },
  { value: 'x4plus-anime', label: 'Real-ESRGAN x4 Anime' },
  { value: 'animevideov3', label: 'Real-ESRGAN Video x4 (Fast)' },
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

const scale = computed(() => variant.value.includes('x2') ? 2 : 4)

const outputResolution = computed(() => {
  if (!props.mediaInfo?.width || !props.mediaInfo?.height) return ''
  const w = props.mediaInfo.width * scale.value
  const h = props.mediaInfo.height * scale.value
  return `${props.mediaInfo.width}×${props.mediaInfo.height} → ${w}×${h}`
})

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return

  const taskId = await submitTask(
    '/video/enhance',
    {
      file_id: props.fileId,
      model: 'realesrgan',
      variant: variant.value,
      output_format: outputFormat.value,
      video_codec: videoCodec.value,
    },
    t('video.enhance.task_label'),
    'video.enhance',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-stars me-2"></i>{{ $t('video.enhance.title') }}</h6>
    <p class="form-hint">{{ $t('video.enhance.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.enhance.variant') }}</label>
      <AppSelect v-model="variant" :options="variantOptions" />
    </div>

    <div v-if="outputResolution" class="form-group resolution-preview">
      <label>{{ $t('video.enhance.output_resolution') }}</label>
      <span class="resolution-text">{{ outputResolution }}</span>
    </div>

    <div class="advanced-toggle" @click="showAdvanced = !showAdvanced">
      <i class="bi" :class="showAdvanced ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
      <span>{{ $t('common.advanced_options') }}</span>
    </div>

    <template v-if="showAdvanced">
      <div class="form-group">
        <label>{{ $t('video.enhance.output_format') }}</label>
        <AppSelect v-model="outputFormat" :options="formatOptions" />
      </div>

      <div class="form-group">
        <label>{{ $t('video.enhance.video_codec') }}</label>
        <AppSelect v-model="videoCodec" :options="codecOptions" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.resolution-preview {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.resolution-text {
  font-size: 0.875rem;
  color: var(--color-primary);
  font-weight: 500;
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
