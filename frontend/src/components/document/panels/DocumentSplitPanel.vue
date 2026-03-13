<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const pages = ref('')
const outputPath = ref('')

const defaultOutputName = computed(() => {
  const stem = props.currentFileName.replace(/\.[^.]+$/, '') || 'output'
  const label = pages.value.trim().replace(/\s/g, '').replace(/,/g, '_') || 'split'
  return `${stem}_p${label}.pdf`
})

const displayOutputPath = computed(() => {
  if (outputPath.value) {
    const parts = outputPath.value.replace(/\\/g, '/').split('/')
    return parts[parts.length - 1]
  }
  return defaultOutputName.value
})

async function selectOutputFile() {
  if ((window as any).electron?.saveFileDialog) {
    const result = await (window as any).electron.saveFileDialog({
      title: '選擇輸出位置',
      defaultPath: defaultOutputName.value,
      filters: [{ name: 'PDF', extensions: ['pdf'] }],
    })
    if (result) outputPath.value = result
  }
}

watch(() => props.fileId, () => { pages.value = ''; outputPath.value = '' })
watch(pages, () => { outputPath.value = '' })

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const body: Record<string, any> = {
    file_id: props.fileId,
    pages: pages.value.trim(),
  }
  if (outputPath.value) {
    const path = outputPath.value.replace(/\\/g, '/')
    const last = path.lastIndexOf('/')
    if (last > 0) {
      body.output_dir      = path.substring(0, last)
      body.output_filename = path.substring(last + 1)
    } else {
      body.output_filename = path
    }
  }
  const taskId = await submitTask('/document/split', body, 'PDF 分割', 'document.split', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-layout-split me-2"></i>分割文件設定</h6>
    <p class="form-hint">依頁碼範圍將 PDF 拆分為獨立檔案。</p>

    <!-- 頁碼範圍 -->
    <div class="form-group">
      <label>頁碼範圍</label>
      <input
        v-model="pages"
        class="form-input"
        type="text"
        placeholder="例：1-3,5,7-9（空白表示全部）"
      />
      <small class="form-hint">以逗號分隔多個範圍，例如 <code>1-3,5,8-10</code></small>
    </div>

    <!-- 輸出檔案 -->
    <div class="form-group">
      <label>輸出檔案</label>
      <div class="file-select" @click="selectOutputFile">
        <span class="file-select-path">{{ displayOutputPath }}</span>
        <i class="bi bi-folder2-open"></i>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

