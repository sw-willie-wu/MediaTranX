<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { apiFetch } from '@/composables/useApi'
import { useModelStore } from '@/stores/models'
import { useModelOptions, parseModelValue } from '@/composables/useModelOptions'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import type { SelectItem } from '@/components/common/AppSelect.vue'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  currentFileExt: string
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const router = useRouter()
const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()
const { guardModelReady } = useModelGuard()

// ── 模型 ──────────────────────────────────────────────────────────────────

const selectedModel = usePersistedModel('doc_ocr_model')
const available = ref<boolean | null>(null)
const modelDownloaded = ref<boolean | null>(null)

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

// ── 輸出選項 ──────────────────────────────────────────────────────────────

const outputFormat = ref<'md' | 'txt'>('md')

const outputFormats = computed(() => [
  { value: 'md',  label: t('document.ocr.markdown') },
  { value: 'txt', label: t('document.ocr.text') },
])

const isPdfOrImage = computed(() => {
  const ext = props.currentFileExt.toLowerCase()
  return ext === 'pdf' || ['png','jpg','jpeg','webp','bmp','tiff','tif'].includes(ext)
})

// ── 狀態載入 ──────────────────────────────────────────────────────────────

async function checkAvailable() {
  const parsed = parseModelValue(selectedModel.value)
  if (parsed.isRemote) {
    available.value = true
    modelDownloaded.value = true
    return
  }
  try {
    const [family, size] = selectedModel.value.split(':')
    const res = await apiFetch(`/document/ocr/status?model_family=${family}&size=${size}`)
    if (!res.ok) return
    const data = await res.json()
    available.value = data.available
    modelDownloaded.value = data.model_downloaded ?? null
  } catch {}
}

onMounted(() => { modelStore.ensureLoaded(); remoteStore.fetchAll(); checkAvailable() })
watch(selectedModel, checkAvailable)

// ── 執行 ──────────────────────────────────────────────────────────────────

const isDisabled = computed(() =>
  !props.fileId || isProcessing.value || !isPdfOrImage.value
)
const isLoading = computed(() => isProcessing.value)

watch(() => modelStore.version, () => checkAvailable())

async function execute() {
  if (!await guardModelReady(modelDownloaded.value === true, 'llm')) return
  if (!props.fileId) return
  const parsed = parseModelValue(selectedModel.value)

  const body: Record<string, any> = {
    file_id: props.fileId,
    format: outputFormat.value,
  }

  if (parsed.isRemote) {
    body.remote = true
    body.provider = parsed.provider
    body.conn_id = parsed.connId
    body.remote_model = parsed.modelId
  } else {
    const [family, size] = selectedModel.value.split(':')
    body.model_family = family
    body.size = size
  }

  const taskId = await submitTask('/document/ocr', body, t('document.ocr.task_label'), 'document.ocr', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

function getParams() {
  const parsed = parseModelValue(selectedModel.value)
  const body: Record<string, any> = {
    format: outputFormat.value,
  }

  if (parsed.isRemote) {
    body.remote = true
    body.provider = parsed.provider
    body.conn_id = parsed.connId
    body.remote_model = parsed.modelId
  } else {
    const [family, size] = selectedModel.value.split(':')
    body.model_family = family
    body.size = size
  }

  return body
}

// ── Agent panel registration ─────────────────────────────────────────────

const flattenOptions = (items: SelectItem[]) =>
  items.flatMap((o: SelectItem) =>
    'options' in o ? o.options.map(x => x.value) : [o.value]
  )

const agentSchema = {
  panelId: 'document.ocr',
  fields: [
    { name: 'model',         type: 'enum' as const, options: () => flattenOptions(modelOptions.value) },
    { name: 'output_format', type: 'enum' as const, options: () => outputFormats.value.map(f => f.value) },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.doc_ocr.execute' },
}

useAgentPanelHost('document.ocr', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    model: selectedModel.value,
    output_format: outputFormat.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'model':         selectedModel.value = String(value);                  return selectedModel.value
      case 'output_format': outputFormat.value  = String(value) as 'md' | 'txt';  return outputFormat.value
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {},
  execute: async () => { await execute(); return {} },
})

defineExpose({ execute, isDisabled, isLoading, outputFormat, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-type me-2"></i>{{ $t('document.ocr.title') }}</h6>
    <p class="form-hint">{{ $t('document.ocr.description') }}</p>

    <div v-if="available === false" class="info-box info-box--warn">
      <i class="bi bi-exclamation-triangle"></i>
      <div class="info-box-body">
        <span>{{ $t('document.ocr.server_not_found') }}</span>
        <button class="info-box-action" @click="router.push('/settings')">{{ $t('document.ocr.go_to_settings') }}</button>
      </div>
    </div>

    <div v-if="!isPdfOrImage && props.fileId" class="info-box info-box--warn">
      <i class="bi bi-info-circle"></i>
      <span>{{ $t('document.ocr.format_not_supported') }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('document.ocr.model') }}</label>
      <AppSelect v-model="selectedModel" :options="modelOptions" />
    </div>

    <div class="form-group">
      <label>{{ $t('document.ocr.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
