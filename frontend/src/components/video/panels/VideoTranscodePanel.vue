<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

const { t } = useI18n()

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const outputFormat = ref('mp4')
const videoCodec = ref('h264')
const resolution = ref('')
const crf = ref(23)
const audioBitrate = ref('192k')
const customResWidth = ref(1920)
const customResHeight = ref(1080)
const scaleAlgorithm = ref('bicubic')

const audioFormatValues = ['mp3', 'aac', 'wav', 'flac']

const formats = computed(() => [
  { value: 'mp4', label: 'MP4' },
  { value: 'mkv', label: 'MKV' },
  { value: 'webm', label: 'WebM' },
  { value: 'avi', label: 'AVI' },
  { value: 'mov', label: 'MOV' },
  { value: 'mp3', label: t('video.transcode.mp3') },
  { value: 'aac', label: t('video.transcode.aac') },
  { value: 'wav', label: t('video.transcode.wav') },
  { value: 'flac', label: t('video.transcode.flac') },
])

const videoCodecs = computed(() => [
  { value: 'h264', label: 'H.264' },
  { value: 'h265', label: 'H.265/HEVC' },
  { value: 'vp9', label: 'VP9' },
  { value: 'copy', label: t('video.transcode.copy_codec') },
])

const resolutions = computed(() => [
  { value: '', label: t('video.transcode.keep_original') },
  { value: '3840x2160', label: '4K (3840x2160)' },
  { value: '2560x1440', label: '2K (2560x1440)' },
  { value: '1920x1080', label: '1080p (1920x1080)' },
  { value: '1280x720', label: '720p (1280x720)' },
  { value: '854x480', label: '480p (854x480)' },
  { value: '640x360', label: '360p (640x360)' },
  { value: 'custom', label: t('video.transcode.custom') },
])

const scaleAlgorithms = computed(() => [
  { value: 'bicubic', label: t('video.transcode.bicubic') },
  { value: 'lanczos', label: t('video.transcode.lanczos') },
  { value: 'spline', label: t('video.transcode.spline') },
  { value: 'bilinear', label: t('video.transcode.bilinear') },
  { value: 'neighbor', label: t('video.transcode.nearest') },
])

const audioBitrates = [
  { value: '128k', label: '128 kbps' },
  { value: '192k', label: '192 kbps' },
  { value: '256k', label: '256 kbps' },
  { value: '320k', label: '320 kbps' },
]

const isAudioFormat = computed(() => audioFormatValues.includes(outputFormat.value))
const showBitrateOption = computed(() => isAudioFormat.value && !['wav', 'flac'].includes(outputFormat.value))

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return

  let taskId: string | null

  if (isAudioFormat.value) {
    taskId = await submitTask(
      '/video/extract-audio',
      {
        file_id: props.fileId,
        audio_format: outputFormat.value,
        audio_bitrate: showBitrateOption.value ? audioBitrate.value : undefined,
      },
      t('video.transcode.extract_audio'),
      'video.extract_audio',
      props.currentFileName,
    )
  } else {
    let finalResolution = resolution.value
    if (resolution.value === 'custom') {
      finalResolution = `${customResWidth.value}x${customResHeight.value}`
    }

    taskId = await submitTask(
      '/video/transcode',
      {
        file_id: props.fileId,
        output_format: outputFormat.value,
        video_codec: videoCodec.value,
        audio_codec: 'aac',
        crf: crf.value,
        resolution: finalResolution || undefined,
        scale_algorithm: finalResolution ? scaleAlgorithm.value : undefined,
      },
      t('video.transcode.task_label'),
      'video.transcode',
      props.currentFileName,
    )
  }

  if (taskId) emit('submit', taskId)
}

function getParams() {
  if (isAudioFormat.value) {
    return {
      audio_format: outputFormat.value,
      audio_bitrate: showBitrateOption.value ? audioBitrate.value : undefined,
    }
  }
  let finalResolution = resolution.value
  if (resolution.value === 'custom') {
    finalResolution = `${customResWidth.value}x${customResHeight.value}`
  }
  return {
    output_format: outputFormat.value,
    video_codec: videoCodec.value,
    audio_codec: 'aac',
    crf: crf.value,
    resolution: finalResolution || undefined,
    scale_algorithm: finalResolution ? scaleAlgorithm.value : undefined,
  }
}

// ── Agent panel registration ──────────────────────────────────────────────────
const agentSchema = {
  panelId: 'video.transcode',
  fields: [
    { name: 'output_format', type: 'enum' as const,
      options: () => formats.value.map(f => f.value) },
    { name: 'video_codec', type: 'enum' as const,
      options: () => videoCodecs.value.map(c => c.value),
      visibleWhen: () => !isAudioFormat.value },
    { name: 'resolution', type: 'enum' as const,
      options: () => resolutions.value.map(r => r.value),
      visibleWhen: () => !isAudioFormat.value },
    { name: 'custom_width', type: 'number' as const,
      min: 1, max: 99999, step: 1,
      visibleWhen: () => resolution.value === 'custom' },
    { name: 'custom_height', type: 'number' as const,
      min: 1, max: 99999, step: 1,
      visibleWhen: () => resolution.value === 'custom' },
    { name: 'scale_algorithm', type: 'enum' as const,
      options: () => scaleAlgorithms.value.map(a => a.value),
      visibleWhen: () => !isAudioFormat.value && !!resolution.value },
    { name: 'crf', type: 'number' as const,
      min: 0, max: 51, step: 1,
      visibleWhen: () => !isAudioFormat.value },
    { name: 'audio_bitrate', type: 'enum' as const,
      options: () => audioBitrates.map(b => b.value),
      visibleWhen: () => showBitrateOption.value },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.transcode.execute' },
}

useAgentPanelHost('video.transcode', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    output_format: outputFormat.value,
    video_codec: videoCodec.value,
    resolution: resolution.value,
    custom_width: customResWidth.value,
    custom_height: customResHeight.value,
    scale_algorithm: scaleAlgorithm.value,
    crf: crf.value,
    audio_bitrate: audioBitrate.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'output_format':
        outputFormat.value = value as string
        return value
      case 'video_codec':
        videoCodec.value = value as string
        return value
      case 'resolution':
        resolution.value = value as string
        return value
      case 'custom_width': {
        const v = Math.max(1, Number(value))
        customResWidth.value = v
        return v
      }
      case 'custom_height': {
        const v = Math.max(1, Number(value))
        customResHeight.value = v
        return v
      }
      case 'scale_algorithm':
        scaleAlgorithm.value = value as string
        return value
      case 'crf': {
        const clamped = Math.min(Math.max(Number(value), 0), 51)
        crf.value = clamped
        return clamped
      }
      case 'audio_bitrate':
        audioBitrate.value = value as string
        return value
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

defineExpose({ execute, isDisabled, isLoading, outputFormat, isAudioFormat, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>{{ $t('video.transcode.title') }}</h6>
    <p class="form-hint">{{ $t('video.transcode.description') }}</p>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="formats" />
    </div>

    <template v-if="!isAudioFormat">
      <div class="form-group">
        <label>{{ $t('video.transcode.resolution') }}</label>
        <AppSelect v-model="resolution" :options="resolutions" />
      </div>

      <div v-if="resolution === 'custom'" class="form-group size-inputs">
        <div class="size-input-group">
          <label>{{ $t('common.width') }}</label>
          <input v-model.number="customResWidth" type="number" class="form-input" min="1" />
        </div>
        <span class="size-separator">x</span>
        <div class="size-input-group">
          <label>{{ $t('common.height') }}</label>
          <input v-model.number="customResHeight" type="number" class="form-input" min="1" />
        </div>
      </div>
    </template>

    <SettingsCollapsible v-if="!isAudioFormat || showBitrateOption" storageKey="video_transcode_advanced">
      <template v-if="!isAudioFormat">
        <div class="form-group">
          <label>{{ $t('video.transcode.video_codec') }}</label>
          <AppSelect v-model="videoCodec" :options="videoCodecs" />
        </div>

        <div v-if="resolution" class="form-group">
          <label>{{ $t('video.transcode.scale_algorithm') }}</label>
          <AppSelect v-model="scaleAlgorithm" :options="scaleAlgorithms" />
        </div>

        <div class="form-group">
          <label>{{ $t('video.transcode.crf') }} {{ crf }}</label>
          <AppRange v-model="crf" :min="0" :max="51" />
          <small class="form-hint">{{ $t('video.transcode.crf_hint') }}</small>
        </div>
      </template>

      <template v-if="showBitrateOption">
        <div class="form-group">
          <label>{{ $t('video.transcode.bitrate') }}</label>
          <AppSelect v-model="audioBitrate" :options="audioBitrates" />
        </div>
      </template>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
