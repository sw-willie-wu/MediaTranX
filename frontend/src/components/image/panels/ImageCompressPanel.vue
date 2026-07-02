<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppRange from '@/components/common/AppRange.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

interface ImageInfo {
  width: number
  height: number
  format: string
  mode: string
  file_size: number
}

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  imageInfo: ImageInfo | null
  isMultiSelect?: boolean
  resultMeta?: Record<string, unknown> | null
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const strength = ref(75)
const gifColors = ref(128)
const gifFrameDrop = ref<number>(0)
const gifOptimizeTransparency = ref(true)
const gifCoalesce = ref(false)
const pngMode = ref<'lossy' | 'lossless'>('lossy')
const jpegProgressive = ref(true)
const jpegKeepMetadata = ref(false)
const webpLossless = ref(false)

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const resultSummary = computed(() => {
  const meta = props.resultMeta
  if (!meta) return null
  const ratio = meta.saved_ratio
  if (typeof ratio !== 'number') return null
  const orig = typeof meta.original_size === 'number' ? meta.original_size : null
  const out  = typeof meta.output_size  === 'number' ? meta.output_size  : null
  const sizeInfo = orig !== null && out !== null
    ? `${formatBytes(orig)} → ${formatBytes(out)}`
    : null
  if (ratio > 0) {
    return { kind: 'saved' as const, pct: Math.round(ratio * 100), sizeInfo }
  } else if (ratio < 0) {
    return { kind: 'larger' as const, pct: Math.round(-ratio * 100), sizeInfo }
  } else {
    return { kind: 'no_change' as const, pct: 0, sizeInfo }
  }
})

const isGif = computed(() => props.imageInfo?.format?.toUpperCase() === 'GIF')
const isPng = computed(() => props.imageInfo?.format?.toUpperCase() === 'PNG')
const isJpeg = computed(() => {
  const fmt = props.imageInfo?.format?.toUpperCase()
  return fmt === 'JPEG' || fmt === 'JPG'
})
const isWebp = computed(() => props.imageInfo?.format?.toUpperCase() === 'WEBP')

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

const gifFrameDropOptions = computed(() => [
  { value: 0, label: t('image.compress.gif_frame_drop_none') },
  { value: 2, label: t('image.compress.gif_frame_drop_2') },
  { value: 3, label: t('image.compress.gif_frame_drop_3') },
  { value: 4, label: t('image.compress.gif_frame_drop_4') },
])

const pngModeOptions = computed(() => [
  { value: 'lossy', label: t('image.compress.png_mode_lossy') },
  { value: 'lossless', label: t('image.compress.png_mode_lossless') },
])

function getParams(): Record<string, unknown> {
  return {
    strength: strength.value,
    gif_colors: gifColors.value,
    gif_frame_drop: gifFrameDrop.value,
    gif_optimize_transparency: gifOptimizeTransparency.value,
    gif_coalesce: gifCoalesce.value,
    png_lossy: pngMode.value === 'lossy',
    jpeg_progressive: jpegProgressive.value,
    jpeg_keep_metadata: jpegKeepMetadata.value,
    webp_lossless: webpLossless.value,
  }
}

async function execute() {
  if (!props.fileId) return

  const taskId = await submitTask(
    '/image/compress',
    {
      file_id: props.fileId,
      ...getParams(),
    },
    t('image.compress.task_label'),
    'image.compress',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

// ── Agent panel registration ──────────────────────────────────────────────────
const agentSchema = {
  panelId: 'image.compress',
  fields: [
    { name: 'strength', type: 'number' as const, min: 1, max: 100, step: 1 },
    { name: 'gif_colors', type: 'number' as const, min: 2, max: 256, step: 1,
      visibleWhen: () => isGif.value },
    { name: 'gif_frame_drop', type: 'enum' as const,
      options: () => ['0', '2', '3', '4'],
      visibleWhen: () => isGif.value },
    { name: 'gif_optimize_transparency', type: 'bool' as const,
      visibleWhen: () => isGif.value },
    { name: 'gif_coalesce', type: 'bool' as const,
      visibleWhen: () => isGif.value },
    { name: 'png_mode', type: 'enum' as const,
      options: () => ['lossy', 'lossless'],
      visibleWhen: () => isPng.value },
    { name: 'jpeg_progressive', type: 'bool' as const,
      visibleWhen: () => isJpeg.value },
    { name: 'jpeg_keep_metadata', type: 'bool' as const,
      visibleWhen: () => isJpeg.value },
    { name: 'webp_lossless', type: 'bool' as const,
      visibleWhen: () => isWebp.value },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.compress.execute' },
}

useAgentPanelHost('image.compress', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    strength: strength.value,
    gif_colors: gifColors.value,
    gif_frame_drop: gifFrameDrop.value,
    gif_optimize_transparency: gifOptimizeTransparency.value,
    gif_coalesce: gifCoalesce.value,
    png_mode: pngMode.value,
    jpeg_progressive: jpegProgressive.value,
    jpeg_keep_metadata: jpegKeepMetadata.value,
    webp_lossless: webpLossless.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'strength': {
        const clamped = Math.min(Math.max(Number(value), 1), 100)
        strength.value = clamped
        return clamped
      }
      case 'gif_colors': {
        const clamped = Math.min(Math.max(Number(value), 2), 256)
        gifColors.value = clamped
        return clamped
      }
      case 'gif_frame_drop':
        gifFrameDrop.value = Number(value)
        return gifFrameDrop.value
      case 'gif_optimize_transparency':
        gifOptimizeTransparency.value = Boolean(value)
        return gifOptimizeTransparency.value
      case 'gif_coalesce':
        gifCoalesce.value = Boolean(value)
        return gifCoalesce.value
      case 'png_mode':
        pngMode.value = value === 'lossless' ? 'lossless' : 'lossy'
        return pngMode.value
      case 'jpeg_progressive':
        jpegProgressive.value = Boolean(value)
        return jpegProgressive.value
      case 'jpeg_keep_metadata':
        jpegKeepMetadata.value = Boolean(value)
        return jpegKeepMetadata.value
      case 'webp_lossless':
        webpLossless.value = Boolean(value)
        return webpLossless.value
      default:
        throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {
    // no-op
  },
  execute: async () => {
    await execute()
    return {}
  },
})

defineExpose({ execute, isDisabled, isLoading, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-file-zip-fill me-2"></i>{{ $t('image.compress.title') }}</h6>
    <p class="form-hint">{{ $t('image.compress.description') }}</p>

    <div v-if="resultSummary" class="compress-result-summary" :class="resultSummary.kind === 'saved' ? 'compress-result-saved' : 'compress-result-neutral'">
      <template v-if="resultSummary.kind === 'saved'">
        <i class="bi bi-check-circle-fill me-1"></i>
        {{ $t('image.compress.saved', { pct: resultSummary.pct }) }}
      </template>
      <template v-else-if="resultSummary.kind === 'larger'">
        <i class="bi bi-exclamation-triangle me-1"></i>
        {{ $t('image.compress.larger', { pct: resultSummary.pct }) }}
      </template>
      <template v-else>
        <i class="bi bi-dash-circle me-1"></i>
        {{ $t('image.compress.no_change') }}
      </template>
      <span v-if="resultSummary.sizeInfo" class="compress-result-sizes">{{ resultSummary.sizeInfo }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('image.compress.strength') }} {{ strength }}%</label>
      <AppRange v-model="strength" :min="1" :max="100" />
      <small class="form-hint">{{ $t('image.compress.strength_hint') }}</small>
    </div>

    <SettingsCollapsible v-if="isPng" storage-key="image_compress_png_advanced">
      <div class="form-group">
        <label>{{ $t('image.compress.png_mode') }}</label>
        <AppSelect v-model="pngMode" :options="pngModeOptions" />
      </div>
    </SettingsCollapsible>

    <SettingsCollapsible v-if="isJpeg" storage-key="image_compress_jpeg_advanced">
      <div class="form-group">
        <AppToggle v-model="jpegProgressive">{{ $t('image.compress.jpeg_progressive') }}</AppToggle>
      </div>
      <div class="form-group">
        <AppToggle v-model="jpegKeepMetadata">{{ $t('image.compress.jpeg_keep_metadata') }}</AppToggle>
      </div>
    </SettingsCollapsible>

    <SettingsCollapsible v-if="isWebp" storage-key="image_compress_webp_advanced">
      <div class="form-group">
        <AppToggle v-model="webpLossless">{{ $t('image.compress.webp_lossless') }}</AppToggle>
      </div>
    </SettingsCollapsible>

    <SettingsCollapsible v-if="isGif" storage-key="image_compress_advanced">
      <div class="form-group">
        <label>{{ $t('image.compress.gif_colors') }} {{ gifColors }}</label>
        <AppRange v-model="gifColors" :min="2" :max="256" />
        <small class="form-hint">{{ $t('image.compress.gif_colors_hint') }}</small>
      </div>

      <div class="form-group">
        <label>{{ $t('image.compress.gif_frame_drop') }}</label>
        <AppSelect v-model="gifFrameDrop" :options="gifFrameDropOptions" />
      </div>

      <div class="form-group">
        <AppToggle v-model="gifOptimizeTransparency">{{ $t('image.compress.gif_optimize_transparency') }}</AppToggle>
      </div>

      <div class="form-group">
        <AppToggle v-model="gifCoalesce">{{ $t('image.compress.gif_coalesce') }}</AppToggle>
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';

.compress-result-summary {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
  margin-bottom: 0.75rem;

  &.compress-result-saved {
    color: var(--text-success, #4caf50);
  }

  &.compress-result-neutral {
    color: var(--text-muted);
  }

  .compress-result-sizes {
    color: var(--text-muted);
    margin-left: 0.25rem;
  }
}
</style>
