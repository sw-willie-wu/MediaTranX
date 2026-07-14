<script setup lang="ts">
/**
 * audio.midi 匯出參數元件（統一參數元件 spec §5；批 3 Task 3.5 Part B——批 3 收官，最小侵入
 * 拆分）。只拆 AudioMidiEditPanel.vue 的 Export tab exportFormat（wav/mp3/flac/ogg/aac
 * select，見 batch3-recon.md §7）。
 *
 * 契約形狀同其他 Params 元件（params/context/fileInfo in、update:params out）以便日後（收尾批
 * 或未來）接入 ToolParamHost/PipelineParamForm——**但本檔無 meta.ts、不進 PARAM_COMPONENTS/
 * METAS、不進 pipeline registry 白名單**：audio.midi 的持久化走 multipart
 * （/audio/midi/create、/audio/midi/convert），無標準 Pydantic request model 可對映
 * ToolParamMeta.schema，不適合三步同構（見 batch3-recon.md §7「audio.midi 不能同構三步」）。
 *
 * 邊界鐵則：本次不改變任何行為。AudioMidiEditPanel.vue 的 getParams/execute/editor/其他
 * tab（Edit/Effects）一行不動——只有 Export tab 的 template 換掛本元件，exportFormat 這顆
 * ref 仍是唯一事實來源，本元件只是它的受控視圖。
 */
import AppSelect from '@/components/common/AppSelect.vue'

const props = defineProps<{
  params: Record<string, unknown>
  context?: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

const exportFormatOptions = [
  { value: 'wav', label: 'WAV' },
  { value: 'mp3', label: 'MP3' },
  { value: 'flac', label: 'FLAC' },
  { value: 'ogg', label: 'OGG' },
  { value: 'aac', label: 'AAC' },
]

function onChange(v: string) {
  emit('update:params', { ...props.params, output_format: v })
}
</script>

<template>
  <div class="form-group">
    <label>{{ $t('audio.midi.export_format') }}</label>
    <AppSelect
      :modelValue="String(params.output_format ?? 'wav')"
      :options="exportFormatOptions"
      @update:modelValue="onChange"
    />
  </div>
</template>
