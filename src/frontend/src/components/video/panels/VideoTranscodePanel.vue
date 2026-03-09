<script setup lang="ts">
import { ref, computed } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
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

const formats = [
  { value: 'mp4', label: 'MP4' },
  { value: 'mkv', label: 'MKV' },
  { value: 'webm', label: 'WebM' },
  { value: 'avi', label: 'AVI' },
  { value: 'mov', label: 'MOV' },
  { value: 'mp3', label: 'MP3（純音訊）' },
  { value: 'aac', label: 'AAC（純音訊）' },
  { value: 'wav', label: 'WAV（純音訊）' },
  { value: 'flac', label: 'FLAC（純音訊）' },
]

const videoCodecs = [
  { value: 'h264', label: 'H.264' },
  { value: 'h265', label: 'H.265/HEVC' },
  { value: 'vp9', label: 'VP9' },
  { value: 'copy', label: '不重新編碼' },
]

const resolutions = [
  { value: '', label: '保持原始' },
  { value: '3840x2160', label: '4K (3840x2160)' },
  { value: '2560x1440', label: '2K (2560x1440)' },
  { value: '1920x1080', label: '1080p (1920x1080)' },
  { value: '1280x720', label: '720p (1280x720)' },
  { value: '854x480', label: '480p (854x480)' },
  { value: 'custom', label: '自訂尺寸' },
]

const scaleAlgorithms = [
  { value: 'bicubic', label: 'Bicubic（預設）' },
  { value: 'lanczos', label: 'Lanczos（高品質）' },
  { value: 'spline', label: 'Spline（高品質）' },
  { value: 'bilinear', label: 'Bilinear（快速）' },
  { value: 'neighbor', label: 'Nearest Neighbor（像素風格）' },
]

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
      '提取音訊',
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
      '轉檔',
      'video.transcode',
      props.currentFileName,
    )
  }

  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, outputFormat, isAudioFormat })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>轉檔</h6>

    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="outputFormat" :options="formats" />
    </div>

    <template v-if="!isAudioFormat">
      <div class="form-group">
        <label>影片編碼</label>
        <AppSelect v-model="videoCodec" :options="videoCodecs" />
      </div>

      <div class="form-group">
        <label>解析度</label>
        <AppSelect v-model="resolution" :options="resolutions" />
      </div>

      <div v-if="resolution === 'custom'" class="form-group size-inputs">
        <div class="size-input-group">
          <label>寬度</label>
          <input v-model.number="customResWidth" type="number" class="form-input" min="1" />
        </div>
        <span class="size-separator">x</span>
        <div class="size-input-group">
          <label>高度</label>
          <input v-model.number="customResHeight" type="number" class="form-input" min="1" />
        </div>
      </div>

      <div v-if="resolution" class="form-group">
        <label>縮放演算法</label>
        <AppSelect v-model="scaleAlgorithm" :options="scaleAlgorithms" />
      </div>

      <div class="form-group">
        <label>品質 (CRF): {{ crf }}</label>
        <AppRange v-model="crf" :min="0" :max="51" />
        <small class="form-hint">數值越小品質越高、檔案越大（建議 18-28）</small>
      </div>
    </template>

    <div v-if="showBitrateOption" class="form-group">
      <label>位元率</label>
      <AppSelect v-model="audioBitrate" :options="audioBitrates" />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
