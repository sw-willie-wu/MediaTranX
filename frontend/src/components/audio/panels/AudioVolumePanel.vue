<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'update:gainPreview': [gain: number]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const mode = ref<'adjust' | 'normalize'>('adjust')
const volumeDb = ref(0)

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

// dB → linear gain: 10^(dB/20)
watch(volumeDb, (db) => {
  emit('update:gainPreview', Math.pow(10, db / 20))
})

const volumeLabel = computed(() => {
  if (volumeDb.value === 0) return t('audio.volume.original')
  return volumeDb.value > 0 ? `+${volumeDb.value} dB` : `${volumeDb.value} dB`
})

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/audio/volume',
    {
      file_id: props.fileId,
      volume_db: mode.value === 'normalize' ? 0 : volumeDb.value,
      normalize: mode.value === 'normalize',
    },
    mode.value === 'normalize' ? t('audio.volume.normalize_label') : t('audio.volume.adjust_label'),
    'audio.volume',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

// ── Agent panel registration ─────
const agentSchema = {
  panelId: 'audio.volume',
  fields: [
    { name: 'mode',      type: 'enum'   as const, options: () => ['adjust', 'normalize'] },
    { name: 'volume_db', type: 'number' as const, min: -20, max: 20, step: 1,
      visibleWhen: () => mode.value === 'adjust' },
  ],
  actions: [],
  execute: { requiresConfirm: false, label: 'panel.volume.execute' },
}

useAgentPanelHost('audio.volume', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({ mode: mode.value, volume_db: volumeDb.value }),
  setField: (field, value) => {
    const clamp = (v: unknown, lo: number, hi: number) => Math.min(Math.max(Number(v), lo), hi)
    switch (field) {
      case 'mode':      mode.value = String(value) as 'adjust' | 'normalize'; return mode.value
      case 'volume_db': { const c = clamp(value, -20, 20); volumeDb.value = c; return c }
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {},  // mode 是 button toggle、no dropdown
  execute: async () => { await execute(); return {} },
})

function getParams() {
  return {
    volume_db: mode.value === 'normalize' ? 0 : volumeDb.value,
    normalize: mode.value === 'normalize',
  }
}

defineExpose({ execute, isDisabled, isLoading, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-volume-up-fill me-2"></i>{{ $t('audio.volume.title') }}</h6>
    <p class="form-hint">{{ $t('audio.volume.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.volume.mode') }}</label>
      <div class="btn-choice-group">
        <button class="btn-choice" :class="{ 'is-active': mode === 'adjust' }" @click="mode = 'adjust'">
          {{ $t('audio.volume.manual') }}
        </button>
        <button class="btn-choice" :class="{ 'is-active': mode === 'normalize' }" @click="mode = 'normalize'">
          {{ $t('audio.volume.normalize') }}
        </button>
      </div>
    </div>

    <template v-if="mode === 'adjust'">
      <div class="form-group">
        <label>{{ $t('audio.volume.volume') }} <span class="param-value">{{ volumeLabel }}</span></label>
        <AppRange v-model="volumeDb" :min="-20" :max="20" :step="1" />
      </div>
    </template>

    <small v-else class="form-hint">
      {{ $t('audio.volume.normalize_hint') }}
    </small>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

