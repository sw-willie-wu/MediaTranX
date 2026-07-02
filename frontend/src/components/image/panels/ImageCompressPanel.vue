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

const isGif = computed(() => props.imageInfo?.format?.toUpperCase() === 'GIF')

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

const gifFrameDropOptions = computed(() => [
  { value: 0, label: t('image.compress.gif_frame_drop_none') },
  { value: 2, label: t('image.compress.gif_frame_drop_2') },
  { value: 3, label: t('image.compress.gif_frame_drop_3') },
  { value: 4, label: t('image.compress.gif_frame_drop_4') },
])

function getParams(): Record<string, unknown> {
  return {
    strength: strength.value,
    gif_colors: gifColors.value,
    gif_frame_drop: gifFrameDrop.value,
    gif_optimize_transparency: gifOptimizeTransparency.value,
    gif_coalesce: gifCoalesce.value,
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

    <div class="form-group">
      <label>{{ $t('image.compress.strength') }} {{ strength }}%</label>
      <AppRange v-model="strength" :min="1" :max="100" />
      <small class="form-hint">{{ $t('image.compress.strength_hint') }}</small>
    </div>

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
</style>
