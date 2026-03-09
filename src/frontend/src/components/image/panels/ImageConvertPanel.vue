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

const convertFormat = ref('png')
const convertQuality = ref(90)
const convertFormats = [
  { value: 'png', label: 'PNG' },
  { value: 'jpg', label: 'JPEG' },
  { value: 'webp', label: 'WebP' },
  { value: 'gif', label: 'GIF' },
  { value: 'bmp', label: 'BMP' },
]

type ResizeMode = 'original' | 'scale' | 'custom'
const convertResizeMode = ref<ResizeMode>('original')
const convertScale = ref(100)
const convertWidth = ref<number | null>(null)
const convertHeight = ref<number | null>(null)

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return

  const taskId = await submitTask(
    '/image/convert',
    {
      file_id: props.fileId,
      output_format: convertFormat.value,
      quality: convertQuality.value,
      scale: convertResizeMode.value === 'scale' ? convertScale.value / 100 : undefined,
      width: convertResizeMode.value === 'custom' ? convertWidth.value ?? undefined : undefined,
      height: convertResizeMode.value === 'custom' ? convertHeight.value ?? undefined : undefined,
    },
    '圖片轉檔',
    'image.convert',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, convertFormat })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>轉檔</h6>

    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="convertFormat" :options="convertFormats" />
    </div>

    <div v-if="convertFormat === 'jpg' || convertFormat === 'webp'" class="form-group">
      <label>品質: {{ convertQuality }}%</label>
      <AppRange v-model="convertQuality" :min="1" :max="100" />
      <small class="form-hint">數值越高品質越好、檔案越大</small>
    </div>

    <div class="form-group">
      <label>尺寸調整</label>
      <AppSelect
        v-model="convertResizeMode"
        :options="[
          { value: 'original', label: '原始尺寸' },
          { value: 'scale', label: '縮放比例' },
          { value: 'custom', label: '自訂尺寸' },
        ]"
      />
    </div>

    <div v-if="convertResizeMode === 'scale'" class="form-group">
      <label>縮放比例: {{ convertScale }}%</label>
      <AppRange v-model="convertScale" :min="10" :max="200" />
      <small class="form-hint">
        {{
          imageInfo
            ? `${imageInfo.width} × ${imageInfo.height} → ${Math.round(imageInfo.width * convertScale / 100)} × ${Math.round(imageInfo.height * convertScale / 100)}`
            : ''
        }}
      </small>
    </div>

    <div v-if="convertResizeMode === 'custom'" class="form-group size-inputs">
      <div class="size-input-group">
        <label>寬度</label>
        <input
          type="number"
          class="form-input"
          placeholder="px"
          :value="convertWidth"
          min="1"
          @input="convertWidth = ($event.target as HTMLInputElement).value ? +($event.target as HTMLInputElement).value : null"
        />
      </div>
      <span class="size-separator">×</span>
      <div class="size-input-group">
        <label>高度</label>
        <input
          type="number"
          class="form-input"
          placeholder="px"
          :value="convertHeight"
          min="1"
          @input="convertHeight = ($event.target as HTMLInputElement).value ? +($event.target as HTMLInputElement).value : null"
        />
      </div>
    </div>
    <small v-if="convertResizeMode === 'custom'" class="form-hint">留空則等比縮放</small>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
