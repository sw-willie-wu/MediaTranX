<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import WhisperAdvancedSettings from '@/components/video/WhisperAdvancedSettings.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { useModelOptions, parseModelValue } from '@/composables/useModelOptions'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'
import type { SelectItem } from '@/components/common/AppSelect.vue'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  language?: string
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()
const { guardModelReady } = useModelGuard()

// Persist both selections separately
const llmModel = usePersistedModel('video_summary_llm_model')
const vlmModel = usePersistedModel('video_summary_vlm_model')

// Summary style: 'bullets' (key points) | 'narrative' (story outline)
const summaryMode = usePersistedModel('video_summary_mode', 'bullets')
const summaryModeOptions = computed(() => [
  { value: 'bullets', label: t('video.summary.mode_bullets') },
  { value: 'narrative', label: t('video.summary.mode_narrative') },
])

// Whisper selections
const whisperModelSize = usePersistedModel('video_summary_whisper_model', 'medium')
const vocalSeparation = ref(false)
const whisperAdvanced = ref<InstanceType<typeof WhisperAdvancedSettings> | null>(null)

// Whisper model options (stt category)
const whisperModelOptions = computed(() =>
  modelStore.forPanel(modelStore.byCategory('stt')).map(m => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  }))
)

// Auto-select first downloaded Whisper model when current is missing/not downloaded
watch(whisperModelOptions, (sizes) => {
  if (sizes.length === 0) return
  const current = sizes.find(m => m.value === whisperModelSize.value)
  if (!current || current.badge !== 'ok') {
    const firstOk = sizes.find(m => m.badge === 'ok')
    if (firstOk) whisperModelSize.value = firstOk.value
  }
}, { immediate: true })

// LLM (text-capable) selector
const localLlmOptions = computed(() => {
  const seen = new Map<string, { value: string; label: string; downloaded: boolean }>()
  for (const m of modelStore.forPanel(modelStore.byCapability('text'))) {
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
const { mergedOptions: llmOptions } = useModelOptions(
  'text', localLlmOptions, { providers: ['ollama', 'openai', 'gemini'] },
)

// VLM (vision-capable) selector — with "none" option for fallback
const localVlmOptions = computed(() => {
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
const { mergedOptions: vlmOptionsBase } = useModelOptions(
  'vision', localVlmOptions, { providers: ['ollama', 'openai', 'gemini'] },
)
const vlmOptions = computed(() => [
  { value: '', label: t('video.summary.vlm_none') },
  ...vlmOptionsBase.value,
])

// Default selection — watch local options (flat list) like ImageOcrPanel
watch(localLlmOptions, (options) => {
  if (!llmModel.value || !options.some(m => m.value === llmModel.value)) {
    const first = options.find(m => m.downloaded)
    llmModel.value = first?.value ?? ''
  }
}, { immediate: true })

onMounted(() => {
  modelStore.ensureLoaded()
  remoteStore.fetchAll()
})

const isDisabled = computed(() => !props.fileId || isProcessing.value || !llmModel.value)
const isLoading = computed(() => isProcessing.value)

// ── Demucs / wav2vec2 readiness ─────────────────────────────────
const demucsReady = computed(() =>
  modelStore.byCategory('separate').some(
    m => m.family === 'demucs' && m.variant === 'htdemucs_6s' && m.downloaded
  )
)
const alignReady = computed(() =>
  modelStore.byCategory('alignment').some(m => m.downloaded)
)

async function execute() {
  if (!props.fileId || !llmModel.value) return

  // Guard: Whisper model (upstream dependency)
  const whisperModel = modelStore.byCategory('stt').find(m => m.variant === whisperModelSize.value)
  if (!await guardModelReady(whisperModel?.downloaded === true, 'audio')) return

  // Guard: Demucs (only when vocal separation is enabled)
  if (vocalSeparation.value) {
    if (!await guardModelReady(demucsReady.value, 'audio')) return
  }
  // Guard: wav2vec2 alignment (only when align is enabled)
  if (whisperAdvanced.value?.align) {
    if (!await guardModelReady(alignReady.value, 'audio')) return
  }

  // Guard: check LLM is downloaded (skip for remote models)
  const llmParsed = parseModelValue(llmModel.value)
  if (!llmParsed.isRemote) {
    const llmLocal = localLlmOptions.value.find(m => m.value === llmModel.value)
    if (!await guardModelReady(!!llmLocal?.downloaded, 'llm')) return
  }

  // Guard: check VLM is downloaded (skip for remote models)
  const vlmParsed = vlmModel.value ? parseModelValue(vlmModel.value) : null
  if (vlmParsed && !vlmParsed.isRemote) {
    const vlmLocal = localVlmOptions.value.find(m => m.value === vlmModel.value)
    if (!await guardModelReady(!!vlmLocal?.downloaded, 'llm')) return
  }

  const params: Record<string, unknown> = {
    file_id: props.fileId,
    language: props.language ?? 'zh-TW',
    whisper_model_size: whisperModelSize.value,
    vocal_separation: vocalSeparation.value,
    summary_mode: summaryMode.value,
  }

  // LLM branch: remote vs local
  if (llmParsed.isRemote) {
    params.llm_remote = true
    params.llm_provider = llmParsed.provider!
    params.llm_conn_id = llmParsed.connId!
    params.llm_remote_model = llmParsed.modelId
  } else {
    const [llmFamily, llmSize] = llmModel.value.split(':')
    params.llm_model_family = llmFamily
    params.llm_model_size = llmSize
  }

  // VLM branch (optional): remote vs local
  if (vlmParsed) {
    if (vlmParsed.isRemote) {
      params.vlm_remote = true
      params.vlm_provider = vlmParsed.provider!
      params.vlm_conn_id = vlmParsed.connId!
      params.vlm_remote_model = vlmParsed.modelId
    } else {
      const [vlmFamily, vlmSize] = vlmModel.value.split(':')
      params.vlm_model_family = vlmFamily
      params.vlm_model_size = vlmSize
    }
  }

  if (whisperAdvanced.value) {
    params.word_timestamps = whisperAdvanced.value.wordTimestamps
    params.align = whisperAdvanced.value.align
    params.condition_on_previous_text = whisperAdvanced.value.conditionOnPreviousText
    params.min_silence_duration_ms = whisperAdvanced.value.minSilenceDurationMs
    params.vad_threshold = whisperAdvanced.value.vadThreshold
  }

  const taskId = await submitTask(
    '/video/summary',
    params,
    t('video.summary.task_label'),
    'video.summary',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

// ── Agent panel registration ─────
const flattenOptions = (items: SelectItem[]) =>
  items.flatMap((o: SelectItem) =>
    'options' in o ? o.options.map(x => x.value) : [o.value]
  )

const agentSchema = {
  panelId: 'video.summary',
  fields: [
    { name: 'whisper_model',    type: 'enum' as const, options: () => whisperModelOptions.value.map(m => m.value) },
    { name: 'llm_model',        type: 'enum' as const, options: () => flattenOptions(llmOptions.value) },
    { name: 'vlm_model',        type: 'enum' as const, options: () => flattenOptions(vlmOptions.value) },
    { name: 'summary_mode',     type: 'enum' as const, options: () => summaryModeOptions.value.map(o => o.value) },
    { name: 'vocal_separation', type: 'bool' as const },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.summary.execute' },
}

useAgentPanelHost('video.summary', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    whisper_model:    whisperModelSize.value,
    llm_model:        llmModel.value,
    vlm_model:        vlmModel.value,
    summary_mode:     summaryMode.value,
    vocal_separation: vocalSeparation.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'whisper_model':    whisperModelSize.value = String(value); return whisperModelSize.value
      case 'llm_model':        llmModel.value         = String(value); return llmModel.value
      case 'vlm_model':        vlmModel.value         = String(value); return vlmModel.value   // 接受 ''
      case 'summary_mode':     summaryMode.value      = String(value); return summaryMode.value
      case 'vocal_separation': vocalSeparation.value  = Boolean(value); return vocalSeparation.value
      default: throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {},
  execute: async () => { await execute(); return {} },
})

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-card-text me-2"></i>{{ $t('video.summary.title') }}
    </h6>
    <p class="form-hint">{{ $t('video.summary.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.summary.mode') }}</label>
      <AppSelect
        v-model="summaryMode"
        :options="summaryModeOptions"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('video.summary.whisper_model') }}</label>
      <AppSelect
        v-model="whisperModelSize"
        :options="whisperModelOptions"
        :placeholder="$t('common.no_models_available')"
      />
    </div>

    <div class="form-group">
      <AppToggle v-model="vocalSeparation">{{ $t('video.summary.vocal_separation') }}</AppToggle>
      <small class="form-hint">{{ $t('video.summary.vocal_separation_hint') }}</small>
    </div>

    <WhisperAdvancedSettings ref="whisperAdvanced" />

    <div class="form-group">
      <label>{{ $t('video.summary.llm_model') }}</label>
      <AppSelect
        v-model="llmModel"
        :options="llmOptions"
        :placeholder="$t('video.summary.select_model')"
      />
      <small class="form-hint">{{ $t('video.summary.llm_model_hint') }}</small>
    </div>

    <div class="form-group">
      <label>{{ $t('video.summary.vlm_model') }}</label>
      <AppSelect
        v-model="vlmModel"
        :options="vlmOptions"
      />
      <small class="form-hint">{{ $t('video.summary.vlm_model_hint') }}</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
