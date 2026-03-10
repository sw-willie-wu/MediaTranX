<script setup lang="ts">
import { ref, computed } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

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
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const outputFormat = ref('jpeg')
const quality = ref(80)

const formatOptions = [
  { value: 'jpeg', label: 'JPEG（照片首選）' },
  { value: 'webp', label: 'WebP（最高壓縮率）' },
  { value: 'png', label: 'PNG（無損壓縮）' },
]

const showQuality = computed(() => outputFormat.value !== 'png')

const fileSizeText = computed(() => {
  if (!props.imageInfo) return ''
  const kb = Math.round(props.imageInfo.file_size / 1024)
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`
})

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/image/compress',
    {
      file_id: props.fileId,
      output_format: outputFormat.value,
      quality: quality.value,
    },
    '圖片壓縮',
    'image.compress',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-file-zip-fill me-2"></i>壓縮設定</h6>
    <p class="form-hint">縮減圖片檔案大小，可設定品質或目標檔案大小。</p>

    <div v-if="imageInfo" class="size-info">
      <i class="bi bi-file-image me-1"></i>
      目前大小：<strong>{{ fileSizeText }}</strong>
    </div>

    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="outputFormat" :options="formatOptions" />
    </div>

    <div v-if="showQuality" class="form-group">
      <label>壓縮品質 <span class="param-value">{{ quality }}%</span></label>
      <AppRange v-model="quality" :min="10" :max="95" :step="5" />
      <small class="form-hint">
        {{ quality >= 80 ? '高品質，壓縮率較低' : quality >= 50 ? '中等品質，壓縮率均衡' : '低品質，壓縮率高' }}
      </small>
    </div>

    <small v-else class="form-hint">
      PNG 為無損壓縮，僅會優化檔案結構，壓縮效果有限。建議改用 JPEG 或 WebP。
    </small>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.size-info {
  font-size: 0.85rem;
  color: var(--text-secondary);
  padding: 0.4rem 0.6rem;
  background: rgba(255,255,255,0.04);
  border-radius: 6px;
  margin-bottom: 0.5rem;
  strong { color: var(--text-primary); }
}
</style>
