<script setup lang="ts">
import { ref, computed } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const outputFormat = ref('mp3')
const bitrate = ref('192k')
const sampleRate = ref('')

const formats = [
  { value: 'mp3',  label: 'MP3' },
  { value: 'aac',  label: 'AAC' },
  { value: 'flac', label: 'FLAC（無損）' },
  { value: 'wav',  label: 'WAV' },
  { value: 'ogg',  label: 'OGG' },
  { value: 'm4a',  label: 'M4A' },
]

const bitrates = [
  { value: '128k', label: '128 kbps' },
  { value: '192k', label: '192 kbps' },
  { value: '256k', label: '256 kbps' },
  { value: '320k', label: '320 kbps' },
]

const sampleRates = [
  { value: '',      label: '保持原始' },
  { value: '44100', label: '44.1 kHz' },
  { value: '48000', label: '48 kHz' },
]

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/audio/transcode',
    {
      file_id: props.fileId,
      output_format: outputFormat.value,
      audio_bitrate: bitrate.value,
      sample_rate: sampleRate.value ? parseInt(sampleRate.value) : null,
    },
    '音訊轉檔',
    'audio.transcode',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>轉檔設定</h6>
    <p class="form-hint">轉換音訊格式，可調整位元率與取樣率。</p>

    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="outputFormat" :options="formats" />
    </div>

    <div class="form-group">
      <label>位元率</label>
      <AppSelect v-model="bitrate" :options="bitrates" />
    </div>

    <div class="form-group">
      <label>取樣率</label>
      <AppSelect v-model="sampleRate" :options="sampleRates" />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
