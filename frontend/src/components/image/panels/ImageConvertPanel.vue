<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
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

const { t } = useI18n()
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

function getParams(): Record<string, unknown> {
  return {
    output_format: convertFormat.value,
    quality: convertQuality.value,
    scale: convertResizeMode.value === 'scale' ? convertScale.value / 100 : undefined,
    width: convertResizeMode.value === 'custom' ? convertWidth.value ?? undefined : undefined,
    height: convertResizeMode.value === 'custom' ? convertHeight.value ?? undefined : undefined,
  }
}

async function execute() {
  if (!props.fileId) return

  const taskId = await submitTask(
    '/image/convert',
    {
      file_id: props.fileId,
      ...getParams(),
    },
    t('image.convert.task_label'),
    'image.convert',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, convertFormat, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>{{ $t('image.convert.title') }}</h6>
    <p class="form-hint">{{ $t('image.convert.description') }}</p>

    <div class="form-group">
      <label>{{ $t('image.convert.output_format') }}</label>
      <AppSelect v-model="convertFormat" :options="convertFormats" />
    </div>

    <div v-if="convertFormat === 'jpg' || convertFormat === 'webp'" class="form-group">
      <label>{{ $t('image.convert.quality') }} {{ convertQuality }}%</label>
      <AppRange v-model="convertQuality" :min="1" :max="100" />
      <small class="form-hint">{{ $t('image.convert.quality_hint') }}</small>
    </div>

    <div class="form-group">
      <label>{{ $t('image.convert.resize_mode') }}</label>
      <AppSelect
        v-model="convertResizeMode"
        :options="[
          { value: 'original', label: $t('image.convert.original_size') },
          { value: 'scale', label: $t('image.convert.scale') },
          { value: 'custom', label: $t('image.convert.custom_size') },
        ]"
      />
    </div>

    <div v-if="convertResizeMode === 'scale'" class="form-group">
      <label>{{ $t('image.convert.scale_label') }} {{ convertScale }}%</label>
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
        <label>{{ $t('image.convert.width') }}</label>
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
        <label>{{ $t('image.convert.height') }}</label>
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
    <small v-if="convertResizeMode === 'custom'" class="form-hint">{{ $t('image.convert.aspect_ratio_hint') }}</small>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
