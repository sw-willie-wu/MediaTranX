<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'

const { t } = useI18n()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  mediaInfo: { fps?: number } | null
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const model = usePersistedModel('interpolate_model', 'v4.26')
const mode = ref('2x')
const targetFps = ref(60)
const outputFormat = ref('mp4')
const videoCodec = ref('h264')

const modelOptions = computed(() =>
  modelStore.forPanel(modelStore.byCategory('interpolate')).map(m => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  }))
)

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

function getParams(): Record<string, unknown> {
  return {
    model: model.value,
    mode: mode.value,
    target_fps: mode.value === 'custom' ? targetFps.value : undefined,
    output_format: outputFormat.value,
    video_codec: videoCodec.value,
  }
}

async function preflight(): Promise<boolean> {
  const selected = modelOptions.value.find(v => v.value === model.value)
  if (!await guardModelReady(selected?.badge === 'ok', 'video')) return false
  return !fpsWarning.value
}

async function execute() {
  if (!await preflight()) return
  if (!props.fileId) return

  const taskId = await submitTask(
    '/video/interpolate',
    { file_id: props.fileId, ...getParams() },
    t('video.interpolate.task_label'),
    'video.interpolate',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

onMounted(() => modelStore.ensureLoaded())

// ── Agent panel registration ─────
const agentSchema = {
  panelId: 'video.interpolate',
  fields: [
    { name: 'model',         type: 'enum'   as const, options: () => modelOptions.value.map(o => o.value) },
    { name: 'mode',          type: 'enum'   as const, options: () => modeOptions.value.map(m => m.value) },
    { name: 'target_fps',    type: 'number' as const, min: 2, max: 240, step: 1,
      visibleWhen: () => mode.value === 'custom' },
    { name: 'output_format', type: 'enum'   as const, options: () => formatOptions.value.map(f => f.value) },
    { name: 'video_codec',   type: 'enum'   as const, options: () => codecOptions.value.map(c => c.value) },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.interpolate.execute' },
}

useAgentPanelHost('video.interpolate', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    model: model.value, mode: mode.value, target_fps: targetFps.value,
    output_format: outputFormat.value, video_codec: videoCodec.value,
  }),
  setField: (field, value) => {
    const clamp = (v: unknown, lo: number, hi: number) => Math.min(Math.max(Number(v), lo), hi)
    switch (field) {
      case 'model':         model.value        = String(value);                  return model.value
      case 'mode':          mode.value         = String(value);                  return mode.value
      case 'target_fps':    { const c = clamp(value, 2, 240); targetFps.value = c; return c }
      case 'output_format': outputFormat.value = String(value);                  return outputFormat.value
      case 'video_codec':   videoCodec.value   = String(value);                  return videoCodec.value
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {},
  execute: async () => { await execute(); return {} },
})

defineExpose({ execute, isDisabled, isLoading, getParams, preflight })
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

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="formatOptions" />
    </div>

    <SettingsCollapsible storage-key="video_interpolate_advanced">
      <div class="form-group">
        <label>{{ $t('video.interpolate.video_codec') }}</label>
        <AppSelect v-model="videoCodec" :options="codecOptions" />
      </div>
    </SettingsCollapsible>
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
</style>
