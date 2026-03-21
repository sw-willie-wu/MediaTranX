<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { apiFetch } from '@/composables/useApi'
import { useModelStore } from '@/stores/models'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  currentFileExt: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const router = useRouter()
const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()

// ── 模型 ──────────────────────────────────────────────────────────────────

const selectedModel = ref('qwen3vl:4b')
const available = ref<boolean | null>(null)

const modelOptions = computed(() => {
  const seen = new Map<string, { value: string; label: string; downloaded: boolean }>()
  for (const m of modelStore.byCategory('vlm')) {
    const [size] = m.variant.split(':')
    const key = `${m.family}:${size}`
    if (!seen.has(key)) {
      const labelNoQuant = m.label.split(' ').slice(0, -1).join(' ')
      seen.set(key, { value: key, label: labelNoQuant, downloaded: m.downloaded })
    } else if (m.downloaded) {
      seen.get(key)!.downloaded = true
    }
  }
  return [...seen.values()].map(opt => ({
    ...opt,
    badge: opt.downloaded ? 'ok' as const : 'err' as const,
  }))
})

// ── 輸出選項 ──────────────────────────────────────────────────────────────

const outputFormat = ref<'md' | 'txt'>('md')
const outputPath = ref('')

const outputFormats = computed(() => [
  { value: 'md',  label: t('document.ocr.markdown') },
  { value: 'txt', label: t('document.ocr.text') },
])

const isPdfOrImage = computed(() => {
  const ext = props.currentFileExt.toLowerCase()
  return ext === 'pdf' || ['png','jpg','jpeg','webp','bmp','tiff','tif'].includes(ext)
})

const defaultOutputName = computed(() => {
  const stem = props.currentFileName.replace(/\.[^.]+$/, '') || 'output'
  return `${stem}_ocr.${outputFormat.value}`
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
    const filter = outputFormat.value === 'md'
      ? { name: 'Markdown', extensions: ['md'] }
      : { name: 'Plain Text', extensions: ['txt'] }
    const result = await (window as any).electron.saveFileDialog({
      title: t('document.ocr.select_output'),
      defaultPath: defaultOutputName.value,
      filters: [filter],
    })
    if (result) outputPath.value = result
  }
}

watch(() => props.fileId, () => { outputPath.value = '' })
watch(outputFormat,       () => { outputPath.value = '' })

// ── 狀態載入 ──────────────────────────────────────────────────────────────

async function checkAvailable() {
  try {
    const [family, size] = selectedModel.value.split(':')
    const res = await apiFetch(`/document/ocr/status?model_id=${family}&size=${size}`)
    if (!res.ok) return
    const data = await res.json()
    available.value = data.available
  } catch {}
}

onMounted(() => { modelStore.ensureLoaded(); checkAvailable() })
watch(selectedModel, checkAvailable)

// ── 執行 ──────────────────────────────────────────────────────────────────

const isDisabled = computed(() =>
  !props.fileId || isProcessing.value || available.value === false || !isPdfOrImage.value
)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const [family, size] = selectedModel.value.split(':')

  const body: Record<string, any> = {
    file_id: props.fileId,
    model_id: family,
    size,
    format: outputFormat.value,
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

  const taskId = await submitTask('/document/ocr', body, t('document.ocr.task_label'), 'document.ocr', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, outputFormat })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-type me-2"></i>{{ $t('document.ocr.title') }}</h6>
    <p class="form-hint">{{ $t('document.ocr.description') }}</p>

    <div v-if="available === false" class="info-box info-box--warn">
      <i class="bi bi-exclamation-triangle"></i>
      <div class="info-box-body">
        <span>{{ $t('document.ocr.server_not_found') }}</span>
        <button class="info-box-action" @click="router.push('/setup')">{{ $t('document.ocr.go_to_settings') }}</button>
      </div>
    </div>

    <div v-if="!isPdfOrImage && props.fileId" class="info-box info-box--warn">
      <i class="bi bi-info-circle"></i>
      <span>{{ $t('document.ocr.format_not_supported') }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('document.ocr.model') }}</label>
      <AppSelect v-model="selectedModel" :options="modelOptions" size="sm" />
    </div>

    <div class="form-group">
      <label>{{ $t('document.ocr.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" size="sm" />
    </div>

    <div class="form-group">
      <label>{{ $t('document.ocr.output_file') }}</label>
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

