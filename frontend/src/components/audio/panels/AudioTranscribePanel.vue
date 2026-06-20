<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import WhisperAdvancedSettings from '@/components/video/WhisperAdvancedSettings.vue'
import TranslationOptionsPanel from '@/components/video/TranslationOptionsPanel.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelOptions, parseModelValue } from '@/composables/useModelOptions'
import { apiFetch } from '@/composables/useApi'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
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

// ── Child component refs ────────────────────────────────────────
const whisperAdvanced = ref<InstanceType<typeof WhisperAdvancedSettings> | null>(null)
const translationOptions = ref<InstanceType<typeof TranslationOptionsPanel> | null>(null)

// ── Whisper model status ────────────────────────────────────────
const modelSizes = computed(() =>
  modelStore.forPanel(modelStore.byCategory('stt')).map(m => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  }))
)

// Auto-select first downloaded model when current selection is not downloaded or not in list
watch(modelSizes, (sizes) => {
  if (sizes.length === 0) return
  const current = sizes.find(m => m.value === modelSize.value)
  if (!current || current.badge !== 'ok') {
    const firstOk = sizes.find(m => m.badge === 'ok')
    if (firstOk) modelSize.value = firstOk.value
  }
})

// ── Settings ────────────────────────────────────────────────────
const modelSize = usePersistedModel('transcribe_whisper_model', 'medium')
const language = ref('')
const outputFormat = ref('txt')
const vocalSeparation = ref(false)
const summarizeEnabled = ref(false)
const selectedSummarizeModel = usePersistedModel('transcribe_summarize_model')

const rawLanguages = ref<{ value: string; label: string }[]>([])

const languages = computed(() =>
  rawLanguages.value.map(item =>
    item.value === '' ? { ...item, label: t('common.auto_detect') } : item
  )
)

async function loadLanguages() {
  try {
    const res = await apiFetch('/audio/transcribe/languages')
    if (res.ok) rawLanguages.value = await res.json()
  } catch {}
}

const outputFormats = computed(() => [
  { value: 'txt', label: t('audio.transcribe.txt_format') },
  { value: 'srt', label: t('audio.transcribe.srt_format') },
])

// ── Summarize model options ─────────────────────────────────────
const localLlmModelOptions = computed(() =>
  modelStore.forPanel(modelStore.byCapability('text'))
    .slice()
    .sort((a, b) => a.size_mb - b.size_mb)
    .map(m => {
      const [size, quant] = m.variant.split(':')
      const key = `${m.family}:${size}:${quant}`
      return { value: key, label: m.label, sizeMb: m.size_mb, badge: m.downloaded ? 'ok' as const : 'err' as const }
    })
)

const { mergedOptions: summarizeModelOptions } = useModelOptions('text', localLlmModelOptions)

watch(localLlmModelOptions, (options) => {
  if (!selectedSummarizeModel.value || !options.some(m => m.value === selectedSummarizeModel.value)) {
    const first = options.find(m => m.badge === 'ok')
    selectedSummarizeModel.value = first?.value ?? ''
  }
}, { immediate: true })

// ── Demucs / wav2vec2 readiness ─────────────────────────────────
const demucsReady = computed(() =>
  modelStore.byCategory('separate').some(
    m => m.family === 'demucs' && m.variant === 'htdemucs_6s' && m.downloaded
  )
)
const alignReady = computed(() =>
  modelStore.byCategory('alignment').some(m => m.downloaded)
)

// ── Submit ──────────────────────────────────────────────────────
async function execute() {
  const whisperModel = modelStore.byCategory('stt').find(m => m.variant === modelSize.value)
  if (!await guardModelReady(whisperModel?.downloaded === true, 'audio')) return
  if (vocalSeparation.value) {
    if (!await guardModelReady(demucsReady.value, 'audio')) return
  }
  if (whisperAdvanced.value?.align) {
    if (!await guardModelReady(alignReady.value, 'audio')) return
  }
  if (translationOptions.value?.enableTranslation) {
    const tParsed = parseModelValue(translationOptions.value.selectedTranslateModel)
    const tModel = translationOptions.value.selectedTranslateModel
    const translateReady = tParsed.isRemote || localLlmModelOptions.value.find(m => m.value === tModel)?.badge === 'ok'
    if (!await guardModelReady(translateReady === true, 'llm')) return
  }
  if (summarizeEnabled.value) {
    const sParsed = parseModelValue(selectedSummarizeModel.value)
    const summarizeReady = sParsed.isRemote || localLlmModelOptions.value.find(m => m.value === selectedSummarizeModel.value)?.badge === 'ok'
    if (!await guardModelReady(summarizeReady === true, 'llm')) return
  }
  if (!props.fileId) return

  const body: Record<string, unknown> = {
    file_id: props.fileId,
    source_language: language.value || null,
    model_size: modelSize.value,
    output_format: outputFormat.value,
    vocal_separation: vocalSeparation.value,
    translate: translationOptions.value?.enableTranslation ?? false,
    summarize: summarizeEnabled.value,
  }

  if (translationOptions.value?.enableTranslation && translationOptions.value.targetLanguage) {
    body.target_language = translationOptions.value.targetLanguage
    const parsed = parseModelValue(translationOptions.value.selectedTranslateModel)
    if (parsed.isRemote) {
      body.translate_remote = true
      body.translate_provider = parsed.provider
      body.translate_conn_id = parsed.connId
      body.translate_remote_model = parsed.modelId
    } else {
      const [tmType, tmSize, tmQuant] = translationOptions.value.selectedTranslateModel.split(':')
      body.translate_model_family = tmType
      body.translate_model_size = tmSize
      body.translate_quantization = tmQuant
    }
    body.keep_names = translationOptions.value.keepNames
    body.translate_style = translationOptions.value.translateStyle
    const glossary = translationOptions.value.parseGlossary()
    if (glossary) body.glossary = glossary
  }

  if (whisperAdvanced.value) {
    body.word_timestamps = whisperAdvanced.value.wordTimestamps
    body.align = whisperAdvanced.value.align
    body.condition_on_previous_text = whisperAdvanced.value.conditionOnPreviousText
    body.min_silence_duration_ms = whisperAdvanced.value.minSilenceDurationMs
    body.vad_threshold = whisperAdvanced.value.vadThreshold
  }

  if (summarizeEnabled.value) {
    const parsed = parseModelValue(selectedSummarizeModel.value)
    if (parsed.isRemote) {
      body.summarize_remote = true
      body.summarize_provider = parsed.provider
      body.summarize_conn_id = parsed.connId
      body.summarize_remote_model = parsed.modelId
    } else {
      const [smType, smSize, smQuant] = selectedSummarizeModel.value.split(':')
      body.summarize_model_family = smType
      body.summarize_model_size = smSize
      body.summarize_quantization = smQuant
    }
  }

  const taskId = await submitTask(
    '/audio/transcribe',
    body,
    t('audio.transcribe.task_label'),
    'audio.transcribe',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

function getParams() {
  const body: Record<string, unknown> = {
    source_language: language.value || null,
    model_size: modelSize.value,
    output_format: outputFormat.value,
    vocal_separation: vocalSeparation.value,
    translate: translationOptions.value?.enableTranslation ?? false,
    summarize: summarizeEnabled.value,
  }

  if (translationOptions.value?.enableTranslation && translationOptions.value.targetLanguage) {
    body.target_language = translationOptions.value.targetLanguage
    const parsed = parseModelValue(translationOptions.value.selectedTranslateModel)
    if (parsed.isRemote) {
      body.translate_remote = true
      body.translate_provider = parsed.provider
      body.translate_conn_id = parsed.connId
      body.translate_remote_model = parsed.modelId
    } else {
      const [tmType, tmSize, tmQuant] = translationOptions.value.selectedTranslateModel.split(':')
      body.translate_model_family = tmType
      body.translate_model_size = tmSize
      body.translate_quantization = tmQuant
    }
    body.keep_names = translationOptions.value.keepNames
    body.translate_style = translationOptions.value.translateStyle
    const glossary = translationOptions.value.parseGlossary()
    if (glossary) body.glossary = glossary
  }

  if (whisperAdvanced.value) {
    body.word_timestamps = whisperAdvanced.value.wordTimestamps
    body.align = whisperAdvanced.value.align
    body.condition_on_previous_text = whisperAdvanced.value.conditionOnPreviousText
    body.min_silence_duration_ms = whisperAdvanced.value.minSilenceDurationMs
    body.vad_threshold = whisperAdvanced.value.vadThreshold
  }

  if (summarizeEnabled.value) {
    const parsed = parseModelValue(selectedSummarizeModel.value)
    if (parsed.isRemote) {
      body.summarize_remote = true
      body.summarize_provider = parsed.provider
      body.summarize_conn_id = parsed.connId
      body.summarize_remote_model = parsed.modelId
    } else {
      const [smType, smSize, smQuant] = selectedSummarizeModel.value.split(':')
      body.summarize_model_family = smType
      body.summarize_model_size = smSize
      body.summarize_quantization = smQuant
    }
  }

  return body
}

// ── Agent panel registration ──────────────────────────────────────────────────
const agentSchema = {
  panelId: 'audio.transcribe',
  fields: [
    { name: 'whisper_model', type: 'enum' as const,
      options: () => modelSizes.value.map(m => m.value) },
    { name: 'language', type: 'enum' as const,
      options: () => languages.value.map(l => l.value) },
    { name: 'output_format', type: 'enum' as const,
      options: () => outputFormats.value.map(f => f.value) },
    { name: 'vocal_separation', type: 'bool' as const },
    { name: 'align', type: 'bool' as const },
    { name: 'translate', type: 'bool' as const },
    { name: 'target_language', type: 'enum' as const,
      options: () => translationOptions.value?.targetLanguageOptions?.map(o => o.value) ?? [],
      visibleWhen: () => translationOptions.value?.enableTranslation ?? false },
    { name: 'summarize', type: 'bool' as const },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.transcribe.execute' },
}

useAgentPanelHost('audio.transcribe', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    whisper_model: modelSize.value,
    language: language.value,
    output_format: outputFormat.value,
    vocal_separation: vocalSeparation.value,
    align: whisperAdvanced.value?.align ?? false,
    translate: translationOptions.value?.enableTranslation ?? false,
    target_language: translationOptions.value?.targetLanguage ?? '',
    summarize: summarizeEnabled.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'whisper_model':
        modelSize.value = value as string
        return value
      case 'language':
        language.value = value as string
        return value
      case 'output_format':
        outputFormat.value = value as string
        return value
      case 'vocal_separation':
        vocalSeparation.value = !!value
        return vocalSeparation.value
      case 'align':
        if (whisperAdvanced.value) whisperAdvanced.value.align = !!value
        return !!value
      case 'translate':
        if (translationOptions.value) translationOptions.value.enableTranslation = !!value
        return !!value
      case 'target_language':
        if (translationOptions.value) translationOptions.value.targetLanguage = value as string
        return value
      case 'summarize':
        summarizeEnabled.value = !!value
        return summarizeEnabled.value
      default:
        throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {
    // no-op
  },
  execute: async () => {
    await execute()
    return {}
  },
})

defineExpose({ execute, isDisabled, isLoading, getParams })

onMounted(() => {
  loadLanguages()
  modelStore.fetchModels()
  remoteStore.ensureLoaded()
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-mic-fill me-2"></i>{{ $t('audio.transcribe.title') }}</h6>
    <p class="form-hint">{{ $t('audio.transcribe.description') }}</p>

    <!-- Basic settings -->
    <div class="form-group">
      <label>{{ $t('audio.transcribe.model') }}</label>
      <AppSelect v-model="modelSize" :options="modelSizes" :placeholder="$t('common.no_models_available')" />
    </div>

    <div class="form-group">
      <label>{{ $t('common.source_language') }}</label>
      <AppSelect v-model="language" :options="languages" />
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>

    <!-- Translation (shared component) -->
    <TranslationOptionsPanel ref="translationOptions" :storageKey="'audio_transcribe_translate_model'" />

    <!-- Summarize -->
    <div class="form-group">
      <AppToggle v-model="summarizeEnabled">{{ $t('audio.transcribe.generate_outline') }}</AppToggle>
      <small class="form-hint">{{ $t('audio.transcribe.generate_outline_hint') }}</small>
    </div>

    <div v-if="summarizeEnabled" class="form-group">
      <label>{{ $t('audio.transcribe.outline_model') }}</label>
      <AppSelect v-model="selectedSummarizeModel" :options="summarizeModelOptions" />
    </div>

    <!-- Advanced: vocal separation + whisper advanced settings -->
    <SettingsCollapsible storageKey="audio_transcribe_advanced">
      <div class="form-group">
        <AppToggle v-model="vocalSeparation">{{ $t('audio.transcribe.vocal_separation') }}</AppToggle>
        <small class="form-hint">{{ $t('audio.transcribe.vocal_separation_hint') }}</small>
      </div>
      <WhisperAdvancedSettings ref="whisperAdvanced" :embedded="true" />
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
