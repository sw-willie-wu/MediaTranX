<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  currentFileExt: string
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const outputFormat = ref('txt')

const isPdf = computed(() => props.currentFileExt === 'pdf')

const outputFormatOptions = computed(() => {
  const opts = [
    { value: 'txt', label: t('document.pdf_convert.text_format') },
    { value: 'md',  label: 'Markdown (.md)' },
  ]
  if (isPdf.value) opts.push({ value: 'images', label: t('document.pdf_convert.images_format') })
  return opts
})

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const body: Record<string, unknown> = {
    file_id: props.fileId,
    output_format: outputFormat.value,
  }
  const taskId = await submitTask('/document/pdf-convert', body, t('document.pdf_convert.task_label'), 'document.pdf_convert', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

function getParams() {
  const body: Record<string, unknown> = {
    output_format: outputFormat.value,
  }
  return body
}

// ── Agent panel registration ─────────────────────────────────────────────

const agentSchema = {
  panelId: 'document.pdf_convert',
  fields: [
    { name: 'output_format', type: 'enum' as const, options: () => outputFormatOptions.value.map(f => f.value) },
  ],
  actions: [],
  execute: { requiresConfirm: false, label: 'panel.doc_pdf_convert.execute' },
}

useAgentPanelHost('document.pdf_convert', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({ output_format: outputFormat.value }),
  setField: (field, value) => {
    switch (field) {
      case 'output_format': outputFormat.value = String(value); return outputFormat.value
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {},
  execute: async () => { await execute(); return {} },
})

defineExpose({ execute, isDisabled, isLoading, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-file-earmark-pdf-fill me-2"></i>{{ $t('document.pdf_convert.title') }}</h6>
    <p class="form-hint">{{ $t('document.pdf_convert.description') }}</p>

    <!-- 輸出格式 -->
    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormatOptions" />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
