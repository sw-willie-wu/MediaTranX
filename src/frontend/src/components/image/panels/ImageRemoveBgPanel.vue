<script setup lang="ts">
import { ref, computed } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const toast = useToast()
const { isProcessing } = useSubmitTask()

const removeBgMode = ref('auto')
const removeBgModes = [
  { value: 'auto', label: '自動偵測' },
  { value: 'person', label: '人物' },
  { value: 'product', label: '商品' },
  { value: 'animal', label: '動物' },
]

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

function execute() {
  toast.show('此功能尚未實作', { type: 'info', icon: 'bi-info-circle' })
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-eraser-fill me-2"></i>去背設定
    </h6>

    <div class="form-group">
      <label>模式</label>
      <AppSelect v-model="removeBgMode" :options="removeBgModes" />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
