<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  sourceDir?: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
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
      title: t('document.split.select_output'),
      defaultPath: defaultOutputName.value,
      filters: [{ name: 'PDF', extensions: ['pdf'] }],
    })
    if (result) outputPath.value = result
  }
}

function resetOutputPath() {
  if (props.sourceDir) {
    const stem = props.currentFileName.replace(/\.[^.]+$/, '') || 'output'
    const label = pages.value.trim().replace(/\s/g, '').replace(/,/g, '_') || 'split'
    outputPath.value = `${props.sourceDir}/${stem}_p${label}.pdf`
  } else {
    outputPath.value = ''
  }
}
watch(() => props.fileId, () => { pages.value = ''; resetOutputPath() })
watch(pages, resetOutputPath)
watch(() => props.sourceDir, resetOutputPath, { immediate: true })

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
  const taskId = await submitTask('/document/split', body, t('document.split.task_label'), 'document.split', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

function getParams() {
  const body: Record<string, any> = {
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
  return body
}

defineExpose({ execute, isDisabled, isLoading, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-layout-split me-2"></i>{{ $t('document.split.title') }}</h6>
    <p class="form-hint">{{ $t('document.split.description') }}</p>

    <!-- 頁碼範圍 -->
    <div class="form-group">
      <label>{{ $t('document.split.page_range') }}</label>
      <input
        v-model="pages"
        class="form-input"
        type="text"
        :placeholder="$t('document.split.range_example')"
      />
      <small class="form-hint">{{ $t('document.split.range_hint', { example: '1-3,5,8-10' }) }}</small>
    </div>

    <!-- 輸出檔案 -->
    <div class="form-group">
      <label>{{ $t('document.split.output_file') }}</label>
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

