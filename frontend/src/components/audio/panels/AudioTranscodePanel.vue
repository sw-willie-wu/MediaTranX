<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const outputFormat = ref('mp3')
const bitrate = ref('192k')
const sampleRate = ref('')

const formats = [
  { group: t('audio.transcode.lossy'), options: [
    { value: 'mp3',  label: 'MP3' },
    { value: 'aac',  label: 'AAC' },
    { value: 'ogg',  label: 'OGG (Vorbis)' },
    { value: 'm4a',  label: 'M4A (AAC)' },
    { value: 'opus', label: 'Opus' },
  ]},
  { group: t('audio.transcode.lossless'), options: [
    { value: 'flac', label: 'FLAC' },
    { value: 'alac', label: 'ALAC' },
    { value: 'wav',  label: 'WAV' },
    { value: 'aiff', label: 'AIFF' },
  ]},
]

// 無損格式不需要 bitrate
const LOSSLESS_FORMATS = new Set(['flac', 'alac', 'wav', 'aiff'])
const showBitrate = computed(() => !LOSSLESS_FORMATS.has(outputFormat.value))

// 各格式最高 bitrate
const FORMAT_MAX_BITRATE: Record<string, string> = {
  mp3: '320k', aac: '512k', m4a: '512k', ogg: '500k', opus: '512k', wma: '384k',
}

const bitrates = computed(() => {
  const max = FORMAT_MAX_BITRATE[outputFormat.value] || '320k'
  const maxNum = parseInt(max)
  const options = [
    { value: '', label: t('audio.transcode.keep_original') },
    { value: '128k', label: '128 kbps' },
    { value: '192k', label: '192 kbps' },
    { value: '256k', label: '256 kbps' },
    { value: '320k', label: '320 kbps' },
  ].filter(o => o.value === '' || parseInt(o.value) <= maxNum)

  if (maxNum > 320) {
    options.push({ value: max, label: `${maxNum} kbps` })
  }

  return options
})

const sampleRates = computed(() => [
  { value: '',      label: t('audio.transcode.keep_original') },
  { value: '44100', label: '44.1 kHz' },
  { value: '48000', label: '48 kHz' },
])

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/audio/transcode',
    {
      file_id: props.fileId,
      output_format: outputFormat.value,
      ...(showBitrate.value && bitrate.value ? { audio_bitrate: bitrate.value } : {}),
      sample_rate: sampleRate.value ? parseInt(sampleRate.value) : null,
    },
    t('audio.transcode.task_label'),
    'audio.transcode',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

function getParams() {
  return {
    output_format: outputFormat.value,
    ...(showBitrate.value && bitrate.value ? { audio_bitrate: bitrate.value } : {}),
    sample_rate: sampleRate.value ? parseInt(sampleRate.value) : null,
  }
}

defineExpose({ execute, isDisabled, isLoading, getParams })

// ── Agent panel registration ─────
const agentSchema = {
  panelId: 'audio.transcode',
  fields: [
    { name: 'output_format', type: 'enum' as const,
      options: () => formats.flatMap(g => g.options.map(o => o.value)) },   // formats is top-level const, no .value
    { name: 'bitrate', type: 'enum' as const,
      options: () => bitrates.value.map(b => b.value),
      visibleWhen: () => showBitrate.value },
    { name: 'sample_rate', type: 'enum' as const,
      options: () => sampleRates.value.map(r => r.value) },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.audio_transcode.execute' },
}

useAgentPanelHost('audio.transcode', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    output_format: outputFormat.value,
    bitrate:       bitrate.value,
    sample_rate:   sampleRate.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'output_format': outputFormat.value = String(value); return outputFormat.value
      case 'bitrate':       bitrate.value      = String(value); return bitrate.value
      case 'sample_rate':   sampleRate.value   = String(value); return sampleRate.value
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {},
  execute: async () => { await execute(); return {} },
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>{{ $t('audio.transcode.title') }}</h6>
    <p class="form-hint">{{ $t('audio.transcode.description') }}</p>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="formats" />
    </div>

    <SettingsCollapsible storage-key="audio_transcode_advanced">
      <div v-if="showBitrate" class="form-group">
        <label>{{ $t('audio.transcode.bitrate') }}</label>
        <AppSelect v-model="bitrate" :options="bitrates" />
      </div>

      <div class="form-group">
        <label>{{ $t('audio.transcode.sample_rate') }}</label>
        <AppSelect v-model="sampleRate" :options="sampleRates" />
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
