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

const removeBgMode = ref('auto')
const removeBgModes = [
  { value: 'auto',    label: '自動偵測' },
  { value: 'person',  label: '人物' },
  { value: 'product', label: '商品' },
  { value: 'animal',  label: '動物' },
]

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/image/remove-bg',
    { file_id: props.fileId, mode: removeBgMode.value },
    '去背',
    'image.remove_bg',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-eraser-fill me-2"></i>去背設定
    </h6>
    <p class="form-hint">自動移除圖片背景，輸出透明底 PNG。</p>

    <div class="form-group">
      <label>主體模式</label>
      <AppSelect v-model="removeBgMode" :options="removeBgModes" />
      <small class="form-hint">自動偵測適合大多數場景</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
