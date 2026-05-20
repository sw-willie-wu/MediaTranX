<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelOptions, parseModelValue } from '@/composables/useModelOptions'
import { apiFetch } from '@/composables/useApi'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useSettingsStore } from '@/stores/settings'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()
const { guardModelReady } = useModelGuard()
const settingsStore = useSettingsStore()

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
const showAdvanced = ref(localStorage.getItem('transcribe_advanced') === 'true')
watch(showAdvanced, (v) => localStorage.setItem('transcribe_advanced', String(v)))
const vocalSeparation = ref(false)
const alignEnabled = ref(false)
const translateEnabled = ref(false)
const targetLanguage = ref('zh-TW')
const selectedTranslateModel = usePersistedModel('transcribe_translate_model')
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

// ── Translation model options ───────────────────────────────────
const localTranslateModelOptions = computed(() =>
  modelStore.forPanel(modelStore.byCapability('text'))
    .slice()
    .sort((a, b) => a.size_mb - b.size_mb)
    .map(m => {
      const [size, quant] = m.variant.split(':')
      const key = `${m.family}:${size}:${quant}`
      return { value: key, label: m.label, sizeMb: m.size_mb, badge: m.downloaded ? 'ok' as const : 'err' as const }
    })
)

const { mergedOptions: translateModelOptions } = useModelOptions('text', localTranslateModelOptions)
const { mergedOptions: summarizeModelOptions } = useModelOptions('text', localTranslateModelOptions)

watch(localTranslateModelOptions, (options) => {
  if (!selectedTranslateModel.value || !options.some(m => m.value === selectedTranslateModel.value)) {
    const first = options.find(m => m.badge === 'ok')
    selectedTranslateModel.value = first?.value ?? ''
  }
  if (!selectedSummarizeModel.value || !options.some(m => m.value === selectedSummarizeModel.value)) {
    const first = options.find(m => m.badge === 'ok')
    selectedSummarizeModel.value = first?.value ?? ''
  }
}, { immediate: true })

// ── Translation language options ────────────────────────────────
const translateLanguages = ref([
  { value: 'zh-TW', label: 'zh-TW' },
  { value: 'zh-CN', label: 'zh-CN' },
  { value: 'en',    label: 'en' },
  { value: 'ja',    label: 'ja' },
  { value: 'ko',    label: 'ko' },
])

async function loadTranslateLanguages() {
  try {
    const res = await apiFetch('/llm/translate/languages')
    if (res.ok) {
      const data = await res.json()
      translateLanguages.value = data.map((l: { code: string; name: string }) => ({
        value: l.code,
        label: l.name,
      }))
    }
  } catch {}
}

watch(translateEnabled, (val) => { if (val) loadTranslateLanguages() })

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
  if (alignEnabled.value) {
    if (!await guardModelReady(alignReady.value, 'audio')) return
  }
  if (translateEnabled.value) {
    const tParsed = parseModelValue(selectedTranslateModel.value)
    const translateReady = tParsed.isRemote || localTranslateModelOptions.value.find(m => m.value === selectedTranslateModel.value)?.badge === 'ok'
    if (!await guardModelReady(translateReady === true, 'llm')) return
  }
  if (summarizeEnabled.value) {
    const sParsed = parseModelValue(selectedSummarizeModel.value)
    const summarizeReady = sParsed.isRemote || localTranslateModelOptions.value.find(m => m.value === selectedSummarizeModel.value)?.badge === 'ok'
    if (!await guardModelReady(summarizeReady === true, 'llm')) return
  }
  if (!props.fileId) return

  const body: Record<string, unknown> = {
    file_id: props.fileId,
    language: language.value || null,
    model_size: modelSize.value,
    output_format: outputFormat.value,
    vocal_separation: vocalSeparation.value,
    align: alignEnabled.value,
    translate: translateEnabled.value,
    summarize: summarizeEnabled.value,
  }

  if (translateEnabled.value && targetLanguage.value) {
    body.target_lang = targetLanguage.value
    const parsed = parseModelValue(selectedTranslateModel.value)
    if (parsed.isRemote) {
      body.translate_remote = true
      body.translate_provider = parsed.provider
      body.translate_conn_id = parsed.connId
      body.translate_remote_model = parsed.modelId
    } else {
      const [tmType, tmSize, tmQuant] = selectedTranslateModel.value.split(':')
      body.translate_model_family = tmType
      body.translate_model_size = tmSize
      body.translate_quantization = tmQuant
    }
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
    language: language.value || null,
    model_size: modelSize.value,
    output_format: outputFormat.value,
    vocal_separation: vocalSeparation.value,
    align: alignEnabled.value,
    translate: translateEnabled.value,
    summarize: summarizeEnabled.value,
  }

  if (translateEnabled.value && targetLanguage.value) {
    body.target_lang = targetLanguage.value
    const parsed = parseModelValue(selectedTranslateModel.value)
    if (parsed.isRemote) {
      body.translate_remote = true
      body.translate_provider = parsed.provider
      body.translate_conn_id = parsed.connId
      body.translate_remote_model = parsed.modelId
    } else {
      const [tmType, tmSize, tmQuant] = selectedTranslateModel.value.split(':')
      body.translate_model_family = tmType
      body.translate_model_size = tmSize
      body.translate_quantization = tmQuant
    }
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

defineExpose({ execute, isDisabled, isLoading, getParams })

onMounted(() => {
  loadLanguages()
  modelStore.fetchModels()
  remoteStore.fetchAll()
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-mic-fill me-2"></i>{{ $t('audio.transcribe.title') }}</h6>
    <p class="form-hint">{{ $t('audio.transcribe.description') }}</p>

    <!-- 基本設定 -->
    <div class="form-group">
      <label>{{ $t('audio.transcribe.model') }}</label>
      <AppSelect v-model="modelSize" :options="modelSizes" :placeholder="$t('common.no_models_available')" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.transcribe.language') }}</label>
      <AppSelect v-model="language" :options="languages" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.transcribe.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>

    <!-- 進階選項（可收合） -->
    <div class="settings-collapsible" :class="{ 'is-open': showAdvanced }">
      <button class="settings-collapsible-header" @click="showAdvanced = !showAdvanced">
        <i class="bi" :class="showAdvanced ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
        <span>{{ $t('common.advanced_options') }}</span>
      </button>

      <div v-if="showAdvanced" class="settings-collapsible-body">
        <div class="form-group">
          <AppToggle v-model="vocalSeparation">{{ $t('audio.transcribe.vocal_separation') }}</AppToggle>
          <small class="form-hint">{{ $t('audio.transcribe.vocal_separation_hint') }}</small>
        </div>

        <div class="form-group">
          <AppToggle v-model="alignEnabled">{{ $t('audio.transcribe.align') }}</AppToggle>
          <small class="form-hint">{{ $t('audio.transcribe.align_hint') }}</small>
        </div>

        <div class="form-group">
          <AppToggle v-model="translateEnabled">{{ $t('audio.transcribe.translate') }}</AppToggle>
          <div v-if="translateEnabled" class="sub-params">
            <div class="form-group">
              <label class="sub-label">{{ $t('audio.transcribe.target_language') }}</label>
              <AppSelect v-model="targetLanguage" :options="translateLanguages" />
            </div>
            <div class="form-group">
              <label class="sub-label">{{ $t('audio.transcribe.translate_model') }}</label>
              <AppSelect v-model="selectedTranslateModel" :options="translateModelOptions" />
            </div>
          </div>
        </div>

        <div class="form-group">
          <AppToggle v-model="summarizeEnabled">{{ $t('audio.transcribe.generate_outline') }}</AppToggle>
          <small class="form-hint">{{ $t('audio.transcribe.generate_outline_hint') }}</small>
        </div>

        <div v-if="summarizeEnabled" class="form-group">
          <label>{{ $t('audio.transcribe.outline_model') }}</label>
          <AppSelect v-model="selectedSummarizeModel" :options="summarizeModelOptions" />
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
