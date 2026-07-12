<script setup lang="ts">
/**
 * image.remove_object 面板殼——批 4 Task 4.5 Part C 拆分後只保留 execute/guard/mask 流程
 * 與標題/描述，工具列 UI（toolMode 選擇器＋brush slider＋清除鈕）已搬到
 * components/params/image/AiRemoveParams.vue（受控 v-model，見該檔檔頭邊界說明）。
 * ⭐鐵則：execute()/guardModelReady()/hasMask()/getMask() 這條流程一行不動。
 */
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AiRemoveParams from '@/components/params/image/AiRemoveParams.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import type { MaskToolMode } from '@/composables/useCanvasMask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  imageInfo: { format?: string } | null
  brushSize: number
  toolMode: MaskToolMode
  getMask: () => string | null
  hasMask: () => boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'update:brushSize': [value: number]
  'update:toolMode': [value: MaskToolMode]
  clearMask: []
}>()

const { t } = useI18n()
const toast = useToast()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const isAnimated = computed(() => {
  const fmt = props.imageInfo?.format?.toUpperCase()
  return fmt === 'GIF' || fmt === 'APNG'
})
const isDisabled = computed(() => !props.fileId || isProcessing.value || isAnimated.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  const segmentDownloaded = modelStore.byCategory('segment').some(m => m.downloaded)
  if (!await guardModelReady(segmentDownloaded, 'image')) return
  if (!props.fileId) return
  if (!props.hasMask()) {
    toast.show(t('toast.mark_area_first'), { type: 'info', icon: 'bi-info-circle' })
    return
  }
  const maskData = props.getMask()
  if (!maskData) return

  const taskId = await submitTask(
    '/image/remove-object',
    { file_id: props.fileId, mask_data: maskData },
    t('image.remove_object.task_label'),
    'image.remove_object',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

onMounted(() => modelStore.ensureLoaded())

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-magic me-2"></i>{{ $t('image.remove_object.title') }}
    </h6>

    <p class="form-hint">{{ $t('image.remove_object.description') }}</p>

    <AiRemoveParams
      :brush-size="brushSize"
      :tool-mode="toolMode"
      :is-disabled="isDisabled"
      @update:brush-size="emit('update:brushSize', $event)"
      @update:tool-mode="emit('update:toolMode', $event)"
      @clear-mask="emit('clearMask')"
    />
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
