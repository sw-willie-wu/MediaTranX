<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import WhisperAdvancedSettings from '@/components/video/WhisperAdvancedSettings.vue'
import TranslationOptionsPanel from '@/components/video/TranslationOptionsPanel.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { apiFetch } from '@/composables/useApi'
import { parseModelValue } from '@/composables/useModelOptions'
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

const { t } = useI18n()

const props = defineProps<{
  fileId: string | null
  mediaInfo: {
    duration: number
    width: number
    height: number
    fps: number
    video_codec: string
    audio_codec: string
    bitrate: number
    file_size: number
  } | null
}>()

const emit = defineEmits<{
  (e: 'submit', taskId: string): void
  (e: 'complete', taskId: string): void
}>()

const filesStore = useFilesStore()
const taskStore = useTaskStore()
const toast = useToast()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const isLoading = ref(false)
const error = ref<string | null>(null)

// ── Whisper 模型狀態 ────────────────────────────────────────────
const modelSizesWithBadge = computed(() =>
  modelStore.forPanel(modelStore.byCategory('stt')).map(m => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  }))
)

// Auto-select first downloaded model when current selection is not downloaded or not in list
watch(modelSizesWithBadge, (sizes) => {
  if (sizes.length === 0) return
  const current = sizes.find(m => m.value === modelSize.value)
  if (!current || current.badge !== 'ok') {
    const firstOk = sizes.find(m => m.badge === 'ok')
    if (firstOk) modelSize.value = firstOk.value
  }
})

// ── 字幕選項 ────────────────────────────────────────────────────
const language = ref('')
const modelSize = usePersistedModel('subtitle_whisper_model', 'medium')
const outputFormat = ref('srt')
const vocalSeparation = ref(false)

// Demucs model (for vocal separation guard)
const demucsModel = computed(() =>
  modelStore.byCategory('separate').find(m => m.family === 'demucs' && m.variant === 'htdemucs_6s')
)

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
  { value: 'srt', label: t('video.subtitle.srt') },
  { value: 'vtt', label: t('video.subtitle.vtt') },
])

// ── 子元件 refs ─────────────────────────────────────────────────
const whisperAdvanced = ref<InstanceType<typeof WhisperAdvancedSettings> | null>(null)
const translationOptions = ref<InstanceType<typeof TranslationOptionsPanel> | null>(null)

// ── wav2vec2 (alignment) readiness ──────────────────────────────
const alignReady = computed(() =>
  modelStore.byCategory('alignment').some(m => m.downloaded)
)

// ── 提交 ────────────────────────────────────────────────────────
async function submitGenerate() {
  const whisperModel = modelStore.byCategory('stt').find(m => m.variant === modelSize.value)
  if (!await guardModelReady(whisperModel?.downloaded === true, 'audio')) return
  if (vocalSeparation.value) {
    if (!await guardModelReady(demucsModel.value?.downloaded === true, 'audio')) return
  }
  if (whisperAdvanced.value?.align) {
    if (!await guardModelReady(alignReady.value, 'audio')) return
  }
  if (translationOptions.value?.enableTranslation) {
    const tParsed = parseModelValue(translationOptions.value.selectedTranslateModel)
    const tModel = translationOptions.value.selectedTranslateModel
    const translateReady = tParsed.isRemote || modelStore.byCapability('text').some(m => {
      const [size, quant] = m.variant.split(':')
      return `${m.family}:${size}:${quant}` === tModel && m.downloaded
    })
    if (!await guardModelReady(translateReady, 'llm')) return
  }
  if (!props.fileId) return
  isLoading.value = true
  error.value = null

  try {
    const body: Record<string, unknown> = {
      file_id: props.fileId,
      model_size: modelSize.value,
      output_format: outputFormat.value,
      vocal_separation: vocalSeparation.value,
    }

    if (language.value) body.source_language = language.value

    if (translationOptions.value?.enableTranslation && translationOptions.value.targetLanguage) {
      const parsed = parseModelValue(translationOptions.value.selectedTranslateModel)
      body.target_language = translationOptions.value.targetLanguage
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

    const response = await apiFetch('/video/subtitle/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Subtitle generation failed')
    }

    const result = await response.json()
    const fileName = filesStore.currentFile?.originalName ?? undefined
    const label = translationOptions.value?.enableTranslation
      ? t('video.subtitle.task_label_with_translate')
      : t('video.subtitle.task_label')
    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'subtitle/generate',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label,
      fileName,
    })
    toast.show(`${t('video.subtitle.start')} ${label}`, { type: 'info', icon: 'bi-badge-cc-fill' })
    emit('submit', result.task_id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    isLoading.value = false
  }
}

const isDisabled = computed(() =>
  isLoading.value || !props.fileId
)

// ── Agent panel registration ──────────────────────────────────────────────────
// NOTE: SubtitlePanel does NOT support multi-select (m16) — hardcoded false.
const agentSchema = {
  panelId: 'video.subtitle',
  fields: [
    { name: 'language', type: 'enum' as const,
      options: () => languages.value.map(l => l.value) },
    { name: 'whisper_model', type: 'enum' as const,
      options: () => modelSizesWithBadge.value.map(m => m.value) },
    { name: 'vocal_separation', type: 'bool' as const },
    { name: 'output_format', type: 'enum' as const,
      options: () => outputFormats.value.map(f => f.value) },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.subtitle.execute' },
}

useAgentPanelHost('video.subtitle', {
  agentSchema,
  isMultiSelect: () => false,  // subtitle panel does not support multi-select
  getCurrentValues: () => ({
    language: language.value,
    whisper_model: modelSize.value,
    vocal_separation: vocalSeparation.value,
    output_format: outputFormat.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'language':
        language.value = value as string
        return value
      case 'whisper_model':
        modelSize.value = value as string
        return value
      case 'vocal_separation':
        vocalSeparation.value = !!value
        return vocalSeparation.value
      case 'output_format':
        outputFormat.value = value as string
        return value
      default:
        throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {
    // no-op
  },
  execute: async () => {
    await submitGenerate()
    return {}
  },
})

defineExpose({ submitGenerate, isLoading, isDisabled })

onMounted(() => { loadLanguages(); modelStore.ensureLoaded() })
</script>

<template>
  <div class="function-settings">
    <div v-if="error" class="info-box info-box--error">
      <i class="bi bi-exclamation-circle"></i>
      <span>{{ error }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('common.source_language') }}</label>
      <AppSelect v-model="language" :options="languages" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.subtitle.model_settings') }}</label>
      <AppSelect v-model="modelSize" :options="modelSizesWithBadge" :placeholder="$t('common.no_models_available')" />
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>

    <TranslationOptionsPanel ref="translationOptions" />

    <WhisperAdvancedSettings ref="whisperAdvanced" />

    <SettingsCollapsible storageKey="video_subtitle_advanced">
      <div class="form-group">
        <AppToggle v-model="vocalSeparation">{{ $t('video.subtitle.vocal_separation') }}</AppToggle>
        <small class="form-hint">{{ $t('video.subtitle.vocal_separation_hint') }}</small>
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
