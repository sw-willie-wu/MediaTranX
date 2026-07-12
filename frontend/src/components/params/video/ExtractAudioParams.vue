<script setup lang="ts">
/**
 * video.extract_audio 參數元件（統一參數元件 spec §5；批 1 Task 1.2）。
 * 契約與核心 pattern 同 CutParams.vue；本元件無需響應式衍生顯示字串（兩欄皆單值 enum
 * select，直接讀 props.params 綁定即可，不需 CutParams 那種本地編輯緩衝）。
 * 純 pipeline 節點用（工具頁沒有獨立掛載點，見 extract_audio.meta.ts 檔頭註解）。
 */
import { computed } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { META as EXTRACT_AUDIO_META } from './extract_audio.meta'

defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

function fieldVisible(params: Record<string, unknown>, name: string): boolean {
  const f = EXTRACT_AUDIO_META.schema.find((x) => x.name === name)
  return f?.visibleWhen ? f.visibleWhen(params) : true
}

const audioFormats = computed(() => [
  { value: 'mp3', label: 'MP3' },
  { value: 'wav', label: 'WAV' },
  { value: 'flac', label: 'FLAC' },
  { value: 'aac', label: 'AAC' },
])

const audioBitrates = [
  { value: '128k', label: '128 kbps' },
  { value: '192k', label: '192 kbps' },
  { value: '256k', label: '256 kbps' },
  { value: '320k', label: '320 kbps' },
]

function commitPatch(params: Record<string, unknown>, patch: Record<string, unknown>) {
  emit('update:params', { ...params, ...patch })
}
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-file-music me-2"></i>{{ $t('video.transcode.extract_audio') }}</h6>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect
        :modelValue="String(params.audio_format ?? 'mp3')"
        :options="audioFormats"
        @update:modelValue="(v) => commitPatch(params, { audio_format: v })"
      />
    </div>

    <div v-if="fieldVisible(params, 'audio_bitrate')" class="form-group">
      <label>{{ $t('video.transcode.bitrate') }}</label>
      <AppSelect
        :modelValue="String(params.audio_bitrate ?? '192k')"
        :options="audioBitrates"
        @update:modelValue="(v) => commitPatch(params, { audio_bitrate: v })"
      />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
