<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
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

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const outputFormat = ref('txt')
const outputPath = ref('')

const isPdf = computed(() => props.currentFileExt === 'pdf')

const outputFormatOptions = computed(() => {
  const opts = [
    { value: 'txt', label: t('document.pdf_convert.text_format') },
    { value: 'md',  label: 'Markdown (.md)' },
  ]
  if (isPdf.value) opts.push({ value: 'images', label: t('document.pdf_convert.images_format') })
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
      txt:    { name: 'Plain Text', extensions: ['txt'] },
      md:     { name: 'Markdown', extensions: ['md'] },
      images: { name: t('document.pdf_convert.zip_type'), extensions: ['zip'] },
    }
    const result = await (window as any).electron.saveFileDialog({
      title: t('document.pdf_convert.select_output'),
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
  const taskId = await submitTask('/document/pdf-convert', body, t('document.pdf_convert.task_label'), 'document.pdf_convert', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-file-earmark-pdf-fill me-2"></i>{{ $t('document.pdf_convert.title') }}</h6>
    <p class="form-hint">{{ $t('document.pdf_convert.description') }}</p>

    <!-- 輸出格式 -->
    <div class="form-group">
      <label>{{ $t('document.pdf_convert.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormatOptions" />
    </div>

    <!-- 輸出檔案 -->
    <div class="form-group">
      <label>{{ $t('document.pdf_convert.output_file') }}</label>
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

