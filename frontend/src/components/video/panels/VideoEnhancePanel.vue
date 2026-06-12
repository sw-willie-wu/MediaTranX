<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'
import AppSelect from '@/components/common/AppSelect.vue'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

const { t } = useI18n()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  mediaInfo: { width?: number; height?: number } | null
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const variant = usePersistedModel('enhance_model', 'x4plus')
const outputFormat = ref('mp4')
const videoCodec = ref('h264')
const showAdvanced = ref(false)

const realesrganModels = computed(() =>
  [...modelStore.forPanel(modelStore.byCategory('upscale')),
   ...modelStore.forPanel(modelStore.byCategory('video_enhance'))]
    .filter(m => m.family === 'realesrgan'))

const variantOptions = computed(() =>
  realesrganModels.value.map(m => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  })))

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

// native scale comes from the model's max_scale (animevideov3 splits into x2/x3/x4,
// so the old `includes('x2')?2:4` heuristic mis-scaled x3). Fall back to it only
// if the model list hasn't loaded yet.
const scale = computed(() =>
  realesrganModels.value.find(m => m.variant === variant.value)?.max_scale
    ?? (variant.value.includes('x2') ? 2 : 4))

const outputResolution = computed(() => {
  if (!props.mediaInfo?.width || !props.mediaInfo?.height) return ''
  const w = props.mediaInfo.width * scale.value
  const h = props.mediaInfo.height * scale.value
  return `${props.mediaInfo.width}×${props.mediaInfo.height} → ${w}×${h}`
})

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  const selected = variantOptions.value.find(v => v.value === variant.value)
  if (!await guardModelReady(selected?.badge === 'ok', 'image')) return
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

onMounted(() => modelStore.ensureLoaded())

// ── Agent panel registration ─────
const agentSchema = {
  panelId: 'video.enhance',
  fields: [
    { name: 'model',         type: 'enum' as const, options: () => variantOptions.value.map(o => o.value) },
    { name: 'output_format', type: 'enum' as const, options: () => formatOptions.value.map(f => f.value) },
    { name: 'video_codec',   type: 'enum' as const, options: () => codecOptions.value.map(c => c.value) },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.enhance.execute' },
}

useAgentPanelHost('video.enhance', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    model:         variant.value,
    output_format: outputFormat.value,
    video_codec:   videoCodec.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'model':         variant.value      = String(value); return variant.value
      case 'output_format': outputFormat.value = String(value); return outputFormat.value
      case 'video_codec':   videoCodec.value   = String(value); return videoCodec.value
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {},
  execute: async () => { await execute(); return {} },
})

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-stars me-2"></i>{{ $t('video.enhance.title') }}</h6>
    <p class="form-hint">{{ $t('video.enhance.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.enhance.model') }}</label>
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
        <label>{{ $t('common.output_format') }}</label>
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
