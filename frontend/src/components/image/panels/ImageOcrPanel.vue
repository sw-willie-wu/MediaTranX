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
import { usePersistedModel } from '@/composables/usePersistedModel'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const router = useRouter()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const selectedModel = usePersistedModel('image_ocr_model')
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
  if (!selectedModel.value || !options.some(m => m.value === selectedModel.value)) {
    const first = options.find(m => m.downloaded)
    selectedModel.value = first?.value ?? ''
  }
}, { immediate: true })

// 合併本地 + 雲端 vision 模型
const { mergedOptions: modelOptions } = useModelOptions('vision', localModelOptions)

const outputFormat = ref<'md' | 'txt'>('md')

const outputFormats = computed(() => [
  { value: 'md',  label: t('image.ocr.markdown') },
  { value: 'txt', label: t('image.ocr.text') },
])

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
    const res = await apiFetch(`/image/ocr/status?model_family=${family}&size=${size}`)
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
    params.model_family = family
    params.size = size
  }
  return params
}

watch(() => modelStore.version, () => checkAvailable())

async function execute() {
  if (!await guardModelReady(modelDownloaded.value === true, 'llm')) return
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
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
