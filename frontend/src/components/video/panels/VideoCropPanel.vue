<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  videoSize: { width: number; height: number } | null
  canvasCropRect?: { x: number; y: number; w: number; h: number } | null
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'update:showCropOverlay': [value: boolean]
  'update:aspectRatio': [value: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const showCropOverlay = ref(true)
watch(showCropOverlay, (val) => emit('update:showCropOverlay', val), { immediate: true })

const x = ref(0)
const y = ref(0)
const cropWidth = ref<number | null>(null)
const cropHeight = ref<number | null>(null)
const aspectRatio = ref('free')
watch(aspectRatio, (val) => emit('update:aspectRatio', val))

const aspectOptions = computed(() => [
  { value: 'free', label: t('video.crop.free') },
  { value: '1:1', label: t('video.crop.square') },
  { value: '4:3', label: '4:3' },
  { value: '3:4', label: '3:4' },
  { value: '16:9', label: '16:9' },
  { value: '9:16', label: '9:16' },
])

// canvas 更新 → 同步到 panel 的輸入欄位
watch(() => props.canvasCropRect, (rect) => {
  if (!rect) return
  x.value = Math.round(rect.x)
  y.value = Math.round(rect.y)
  cropWidth.value = Math.round(rect.w)
  cropHeight.value = Math.round(rect.h)
})

watch([aspectRatio, cropWidth], ([ratio]) => {
  if (ratio === 'free' || !cropWidth.value) return
  const [wRatio, hRatio] = ratio.split(':').map(Number)
  cropHeight.value = Math.round(cropWidth.value * hRatio / wRatio)
})

const maxW = computed(() => props.videoSize ? props.videoSize.width - x.value : 9999)
const maxH = computed(() => props.videoSize ? props.videoSize.height - y.value : 9999)

const isDisabled = computed(() => !props.fileId || isProcessing.value || !cropWidth.value || !cropHeight.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId || !cropWidth.value || !cropHeight.value) return
  const taskId = await submitTask(
    '/video/crop',
    {
      file_id: props.fileId,
      x: x.value,
      y: y.value,
      width: cropWidth.value,
      height: cropHeight.value,
    },
    t('video.crop.task_label'),
    'video.crop',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, showCropOverlay, aspectRatio })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-crop me-2"></i>{{ $t('video.crop.title') }}</h6>
    <p class="form-hint">{{ $t('video.crop.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.crop.aspect_ratio') }}</label>
      <AppSelect v-model="aspectRatio" :options="aspectOptions" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.crop.start_position') }}</label>
      <div class="coord-row">
        <div class="coord-field">
          <span class="coord-label">X</span>
          <input type="number" class="form-input" v-model.number="x"
            :min="0" :max="videoSize ? videoSize.width - 1 : 9999" placeholder="0" />
        </div>
        <div class="coord-field">
          <span class="coord-label">Y</span>
          <input type="number" class="form-input" v-model.number="y"
            :min="0" :max="videoSize ? videoSize.height - 1 : 9999" placeholder="0" />
        </div>
      </div>
    </div>

    <div class="form-group">
      <label>{{ $t('video.crop.crop_size') }}</label>
      <div class="coord-row">
        <div class="coord-field">
          <span class="coord-label">{{ $t('image.convert.width') }}</span>
          <input type="number" class="form-input" v-model.number="cropWidth"
            :min="1" :max="maxW" placeholder="px" />
        </div>
        <div class="coord-field">
          <span class="coord-label">{{ $t('image.convert.height') }}</span>
          <input type="number" class="form-input" v-model.number="cropHeight"
            :min="1" :max="maxH" placeholder="px"
            :disabled="aspectRatio !== 'free'" />
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.coord-row {
  display: flex;
  gap: 8px;
}

.coord-field {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;

  .coord-label {
    font-size: 0.8rem;
    color: var(--text-muted);
    white-space: nowrap;
    min-width: 12px;
  }

  .form-input {
    flex: 1;
    min-width: 0;
  }
}
</style>
