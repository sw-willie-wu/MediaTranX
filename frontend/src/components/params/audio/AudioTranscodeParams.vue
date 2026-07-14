<script setup lang="ts">
/**
 * audio.transcode 參數元件（統一參數元件 spec §5；批 3 Task 3.1）。
 * 命名刻意用 AudioTranscodeParams（非 TranscodeParams）——避免與
 * components/params/video/TranscodeParams.vue 撞名（見 batch3-recon.md 檔頭約束）。
 *
 * UI 全沿舊 components/audio/panels/AudioTranscodePanel.vue：格式 AppSelect 分組
 * lossy/lossless（wma 有 schema、UI 選單不列——舊 panel formats 常量本就沒有 wma，
 * 見 transcode.meta.ts 檔頭註解）；進階區 bitrate（動態上限 FORMAT_MAX_BITRATE，
 * 無損格式隱藏）＋sample_rate（''/44100/48000）＋新增 channels（''/1/2，後端有此欄、
 * 舊 panel 無 UI——佈局鐵則落 advanced）。
 *
 * 全部欄位皆為下拉選單（無自由文字輸入框），故不需要 CutParams/CropParams 那套
 * one-shot lastEmitted 本地緩衝——顯示值直接是 props.params 的響應式衍生（同
 * video/TranscodeParams.vue 除 resolution 外其餘欄位的作法）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { META as TRANSCODE_META, LOSSLESS_FORMATS } from './transcode.meta'

const { t } = useI18n()

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

function commitPatch(patch: Record<string, unknown>) {
  emit('update:params', { ...props.params, ...patch })
}

function fieldVisible(name: string): boolean {
  const f = TRANSCODE_META.schema.find((x) => x.name === name)
  return f?.visibleWhen ? f.visibleWhen(props.params) : true
}

const outputFormat = computed(() => String(props.params.output_format ?? 'mp3'))
const isLossless = computed(() => LOSSLESS_FORMATS.has(outputFormat.value))
const bitrateVisible = computed(() => fieldVisible('audio_bitrate') && !isLossless.value)

// ── 選項清單（沿舊 AudioTranscodePanel 常量；wma 不入選單） ──────────────────
const formats = computed(() => [
  { group: t('audio.transcode.lossy'), options: [
    { value: 'mp3', label: 'MP3' },
    { value: 'aac', label: 'AAC' },
    { value: 'ogg', label: 'OGG (Vorbis)' },
    { value: 'm4a', label: 'M4A (AAC)' },
    { value: 'opus', label: 'Opus' },
  ] },
  { group: t('audio.transcode.lossless'), options: [
    { value: 'flac', label: 'FLAC' },
    { value: 'alac', label: 'ALAC' },
    { value: 'wav', label: 'WAV' },
    { value: 'aiff', label: 'AIFF' },
  ] },
])

// 各格式最高 bitrate（沿舊 panel；wma 不在 UI 選單但常量保留無害）
const FORMAT_MAX_BITRATE: Record<string, string> = {
  mp3: '320k', aac: '512k', m4a: '512k', ogg: '500k', opus: '512k', wma: '384k',
}

const bitrates = computed(() => {
  const max = FORMAT_MAX_BITRATE[outputFormat.value] || '320k'
  const maxNum = parseInt(max, 10)
  const options = [
    { value: '', label: t('audio.transcode.keep_original') },
    { value: '128k', label: '128 kbps' },
    { value: '192k', label: '192 kbps' },
    { value: '256k', label: '256 kbps' },
    { value: '320k', label: '320 kbps' },
  ].filter((o) => o.value === '' || parseInt(o.value, 10) <= maxNum)
  if (maxNum > 320) options.push({ value: max, label: `${maxNum} kbps` })
  return options
})

const sampleRates = computed(() => [
  { value: '', label: t('audio.transcode.keep_original') },
  { value: '44100', label: '44.1 kHz' },
  { value: '48000', label: '48 kHz' },
])

const channelsOptions = computed(() => [
  { value: '', label: t('audio.transcode.keep_original') },
  { value: '1', label: t('audio.transcode.mono') },
  { value: '2', label: t('audio.transcode.stereo') },
])

const sampleRateValue = computed(() =>
  typeof props.params.sample_rate === 'number' ? String(props.params.sample_rate) : '',
)
const channelsValue = computed(() =>
  typeof props.params.channels === 'number' ? String(props.params.channels) : '',
)

function onFormatChange(v: string) {
  commitPatch({ output_format: v })
}
function onBitrateChange(v: string) {
  commitPatch({ audio_bitrate: v })
}
function onSampleRateChange(v: string) {
  commitPatch({ sample_rate: v === '' ? undefined : Number(v) })
}
function onChannelsChange(v: string) {
  commitPatch({ channels: v === '' ? undefined : Number(v) })
}
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>{{ $t('audio.transcode.title') }}</h6>
    <p class="form-hint">{{ $t('audio.transcode.description') }}</p>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect :modelValue="outputFormat" :options="formats" @update:modelValue="onFormatChange" />
    </div>

    <SettingsCollapsible storage-key="audio_transcode_advanced">
      <div v-if="bitrateVisible" class="form-group">
        <label>{{ $t('audio.transcode.bitrate') }}</label>
        <AppSelect
          :modelValue="String(params.audio_bitrate ?? '')"
          :options="bitrates"
          @update:modelValue="onBitrateChange"
        />
      </div>

      <div class="form-group">
        <label>{{ $t('audio.transcode.sample_rate') }}</label>
        <AppSelect :modelValue="sampleRateValue" :options="sampleRates" @update:modelValue="onSampleRateChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('audio.transcode.channels') }}</label>
        <AppSelect :modelValue="channelsValue" :options="channelsOptions" @update:modelValue="onChannelsChange" />
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
