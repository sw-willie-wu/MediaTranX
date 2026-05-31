<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import type { FilterPreview } from './filterTypes'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'preview-change': [preview: FilterPreview]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const brightness = ref(100)
const contrast   = ref(100)
const saturation = ref(100)
const hue        = ref(0)
const sharpness  = ref(100)
const warmth     = ref(0)

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

const preview = computed<FilterPreview>(() => ({
  brightness: brightness.value / 100,
  contrast:   contrast.value / 100,
  saturation: saturation.value / 100,
  hue:        hue.value,
  sharpness:  sharpness.value / 100,
  warmth:     warmth.value / 100,
  grayscale:  0,
  sepia:      0,
  invert:     0,
  blur:       0,
  vignette:   0,
}))

watch(preview, (val) => emit('preview-change', val), { immediate: true })

export interface AdjustState {
  brightness: number
  contrast:   number
  saturation: number
  hue:        number
  sharpness:  number
  warmth:     number
}

function getState(): AdjustState {
  return {
    brightness: brightness.value,
    contrast:   contrast.value,
    saturation: saturation.value,
    hue:        hue.value,
    sharpness:  sharpness.value,
    warmth:     warmth.value,
  }
}

function setState(s: AdjustState) {
  brightness.value = s.brightness
  contrast.value   = s.contrast
  saturation.value = s.saturation
  hue.value        = s.hue
  sharpness.value  = s.sharpness
  warmth.value     = s.warmth
}

function reset() {
  brightness.value = 100
  contrast.value   = 100
  saturation.value = 100
  hue.value        = 0
  sharpness.value  = 100
  warmth.value     = 0
}

function getParams(): Record<string, unknown> {
  return {
    brightness: brightness.value / 100,
    contrast:   contrast.value / 100,
    saturation: saturation.value / 100,
    hue:        hue.value,
    sharpness:  sharpness.value / 100,
    warmth:     warmth.value / 100,
  }
}

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/image/filter',
    { file_id: props.fileId, ...getParams() },
    t('image.adjust.task_label'),
    'image.filter',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

// ── Agent panel registration ─────────────────────────────────────────────────
const agentSchema = {
  panelId: 'image.adjust',
  fields: [
    { name: 'brightness', type: 'number' as const, min: 0,    max: 300, step: 1 },
    { name: 'contrast',   type: 'number' as const, min: 0,    max: 300, step: 1 },
    { name: 'saturation', type: 'number' as const, min: 0,    max: 300, step: 1 },
    { name: 'sharpness',  type: 'number' as const, min: 0,    max: 300, step: 1 },
    { name: 'hue',        type: 'number' as const, min: -180, max: 180, step: 1 },
    { name: 'warmth',     type: 'number' as const, min: -100, max: 100, step: 1 },
  ],
  actions: [{ name: 'reset', label: 'image.adjust.reset' }],
  execute: { requiresConfirm: false, label: 'panel.adjust.execute' },
}

useAgentPanelHost('image.adjust', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    brightness: brightness.value, contrast: contrast.value, saturation: saturation.value,
    sharpness: sharpness.value, hue: hue.value, warmth: warmth.value,
  }),
  setField: (field, value) => {
    const clamp = (v: unknown, lo: number, hi: number) => Math.min(Math.max(Number(v), lo), hi)
    switch (field) {
      case 'brightness': { const c = clamp(value, 0, 300); brightness.value = c; return c }
      case 'contrast':   { const c = clamp(value, 0, 300); contrast.value = c;   return c }
      case 'saturation': { const c = clamp(value, 0, 300); saturation.value = c; return c }
      case 'sharpness':  { const c = clamp(value, 0, 300); sharpness.value = c;  return c }
      case 'hue':        { const c = clamp(value, -180, 180); hue.value = c;     return c }
      case 'warmth':     { const c = clamp(value, -100, 100); warmth.value = c;  return c }
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {},
  invokeAction: (name) => { if (name === 'reset') reset() },
  execute: async () => { await execute(); return {} },
})

defineExpose({ execute, isDisabled, isLoading, getState, setState, reset, getParams, getPreview: () => preview.value })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-sliders me-2"></i>{{ $t('image.adjust.title') }}</h6>
    <p class="form-hint">{{ $t('image.adjust.description') }}</p>

    <div class="form-group">
      <label>{{ $t('image.adjust.brightness') }} <span class="param-value">{{ brightness }}%</span></label>
      <AppRange v-model="brightness" :min="0" :max="300" :step="1" />
    </div>

    <div class="form-group">
      <label>{{ $t('image.adjust.contrast') }} <span class="param-value">{{ contrast }}%</span></label>
      <AppRange v-model="contrast" :min="0" :max="300" :step="1" />
    </div>

    <div class="form-group">
      <label>{{ $t('image.adjust.saturation') }} <span class="param-value">{{ saturation }}%</span></label>
      <AppRange v-model="saturation" :min="0" :max="300" :step="1" />
    </div>

    <div class="form-group">
      <label>{{ $t('image.adjust.sharpness') }} <span class="param-value">{{ sharpness }}%</span></label>
      <AppRange v-model="sharpness" :min="0" :max="300" :step="1" />
    </div>

    <div class="form-group">
      <label>{{ $t('image.adjust.hue') }} <span class="param-value">{{ hue > 0 ? '+' : '' }}{{ hue }}°</span></label>
      <AppRange v-model="hue" :min="-180" :max="180" :step="1" />
    </div>

    <div class="form-group">
      <label>
        {{ $t('image.adjust.warmth') }}
        <span class="param-value">
          {{ warmth > 0 ? `${$t('image.adjust.warm')} +${warmth}` : warmth < 0 ? `${$t('image.adjust.cool')} ${warmth}` : '0' }}
        </span>
      </label>
      <AppRange v-model="warmth" :min="-100" :max="100" :step="1" />
    </div>

    <div class="form-group">
      <button class="btn-secondary" @click="reset">
        <i class="bi bi-arrow-counterclockwise"></i>{{ $t('image.adjust.reset') }}
      </button>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
