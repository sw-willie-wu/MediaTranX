<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { apiFetch } from '@/composables/useApi'
import { useModelStore } from '@/stores/models'
import { useModelOptions, parseModelValue } from '@/composables/useModelOptions'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { useModelGuard } from '@/composables/useModelGuard'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  sourceDir?: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const router = useRouter()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const selectedModel = ref('')
const available = ref<boolean | null>(null)
const modelDownloaded = ref<boolean | null>(null)

const remoteStore = useRemoteModelStore()

// 從 store 的 vlm 模型列表聚合（依 family:size 去重）
const localModelOptions = computed(() => {
  const seen = new Map<string, { value: string; label: string; downloaded: boolean }>()
  for (const m of modelStore.forPanel(modelStore.byCapability('vision'))) {
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

watch(localModelOptions, (options) => {
  if (!selectedModel.value) {
    const first = options.find(m => m.downloaded)
    if (first) selectedModel.value = first.value
  }
}, { immediate: true })

// 合併本地 + 雲端 vision 模型
const { mergedOptions: modelOptions } = useModelOptions('vision', localModelOptions)

const outputFormat = ref<'md' | 'txt'>('md')
const outputPath = ref('')

const outputFormats = computed(() => [
  { value: 'md',  label: t('image.ocr.markdown') },
  { value: 'txt', label: t('image.ocr.text') },
])

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
      : { name: t('image.ocr.text'), extensions: ['txt'] }
    const result = await (window as any).electron.saveFileDialog({
      title: t('image.ocr.select_output'),
      defaultPath: defaultOutputName.value,
      filters: [filter],
    })
    if (result) outputPath.value = result
  }
}

function resetOutputPath() {
  if (props.sourceDir) {
    const stem = props.currentFileName.replace(/\.[^.]+$/, '') || 'output'
    outputPath.value = `${props.sourceDir}/${stem}_ocr.${outputFormat.value}`
  } else {
    outputPath.value = ''
  }
}
watch(() => props.fileId, resetOutputPath)
watch(outputFormat, resetOutputPath)
watch(() => props.sourceDir, resetOutputPath, { immediate: true })

async function checkAvailable() {
  const parsed = parseModelValue(selectedModel.value)
  if (parsed.isRemote) {
    // 雲端模型不需要檢查本地 server
    available.value = true
    modelDownloaded.value = true
    return
  }
  try {
    const [family, size] = selectedModel.value.split(':')
    const res = await apiFetch(`/image/ocr/status?model_id=${family}&size=${size}`)
    if (!res.ok) return
    const data = await res.json()
    available.value = data.available
    modelDownloaded.value = data.model_downloaded ?? null
  } catch {}
}

onMounted(() => {
  modelStore.ensureLoaded()
  remoteStore.fetchAll()
  checkAvailable()
})
watch(selectedModel, checkAvailable)

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

function getParams(): Record<string, unknown> {
  const parsed = parseModelValue(selectedModel.value)
  const params: Record<string, unknown> = {
    format: outputFormat.value,
  }

  if (parsed.isRemote) {
    params.remote = true
    params.provider = parsed.provider
    params.conn_id = parsed.connId
    params.remote_model = parsed.modelId
  } else {
    const [family, size] = selectedModel.value.split(':')
    params.model_id = family
    params.size = size
  }
  if (outputPath.value) {
    const path = outputPath.value.replace(/\\/g, '/')
    const lastSlash = path.lastIndexOf('/')
    if (lastSlash > 0) {
      params.output_dir      = path.substring(0, lastSlash)
      params.output_filename = path.substring(lastSlash + 1)
    } else {
      params.output_filename = path
    }
  }
  return params
}

async function execute() {
  if (!await guardModelReady(modelDownloaded.value !== false, 'llm')) return
  if (!props.fileId) return
  const taskId = await submitTask(
    '/image/ocr',
    { file_id: props.fileId, ...getParams() },
    t('image.ocr.task_label'),
    'image.ocr',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, outputFormat, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-type me-2"></i>{{ $t('image.ocr.title') }}</h6>
    <p class="form-hint">{{ $t('image.ocr.description') }}</p>

    <div v-if="available === false" class="info-box info-box--warn">
      <i class="bi bi-exclamation-triangle"></i>
      <div class="info-box-body">
        <span>{{ $t('image.ocr.server_not_found') }}</span>
        <button class="info-box-action" @click="router.push('/settings')">{{ $t('image.ocr.go_to_settings') }}</button>
      </div>
    </div>

    <div class="form-group">
      <label>{{ $t('image.ocr.model') }}</label>
      <AppSelect v-model="selectedModel" :options="modelOptions" />
    </div>

    <div class="form-group">
      <label>{{ $t('image.ocr.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>

    <div class="form-group">
      <label>{{ $t('image.ocr.output_file') }}</label>
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
