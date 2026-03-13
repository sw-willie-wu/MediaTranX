<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  currentFileExt: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const outputFormat = ref('txt')
const outputPath = ref('')

const isPdf = computed(() => props.currentFileExt === 'pdf')

const outputFormatOptions = computed(() => {
  const opts = [
    { value: 'txt', label: '純文字 (.txt)' },
    { value: 'md',  label: 'Markdown (.md)' },
  ]
  if (isPdf.value) opts.push({ value: 'images', label: '頁面圖片 (.zip)' })
  return opts
})

const extMap: Record<string, string> = { txt: 'txt', md: 'md', images: 'zip' }

const defaultOutputName = computed(() => {
  const stem = props.currentFileName.replace(/\.[^.]+$/, '') || 'output'
  return `${stem}_converted.${extMap[outputFormat.value] ?? 'txt'}`
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
    const filterMap: Record<string, { name: string; extensions: string[] }> = {
      txt:    { name: '純文字', extensions: ['txt'] },
      md:     { name: 'Markdown', extensions: ['md'] },
      images: { name: 'ZIP 壓縮檔', extensions: ['zip'] },
    }
    const result = await (window as any).electron.saveFileDialog({
      title: '選擇輸出位置',
      defaultPath: defaultOutputName.value,
      filters: [filterMap[outputFormat.value]],
    })
    if (result) outputPath.value = result
  }
}

watch(() => props.fileId, () => { outputPath.value = '' })
watch(outputFormat, () => { outputPath.value = '' })

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const body: Record<string, any> = {
    file_id: props.fileId,
    output_format: outputFormat.value,
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
  const taskId = await submitTask('/document/pdf-convert', body, 'PDF 轉換', 'document.pdf_convert', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-file-earmark-pdf-fill me-2"></i>PDF 轉換設定</h6>
    <p class="form-hint">將 PDF 轉換為純文字、Markdown 或頁面圖片。</p>

    <!-- 輸出格式 -->
    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="outputFormat" :options="outputFormatOptions" size="sm" />
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

