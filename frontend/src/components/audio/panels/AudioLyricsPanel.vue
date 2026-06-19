<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import TranslationOptionsPanel from '@/components/video/TranslationOptionsPanel.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { parseModelValue } from '@/composables/useModelOptions'
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
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()
const { guardModelReady } = useModelGuard()

// ── Child component refs ────────────────────────────────────────
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
const modelSize = usePersistedModel('lyrics_whisper_model', 'medium')
const alignEnabled = ref(false)
const outputFormat = ref('lrc')

const outputFormats = computed(() => [
  { value: 'lrc', label: t('audio.lyrics.lrc') },
  { value: 'txt', label: t('audio.lyrics.txt') },
])

// ── Demucs / wav2vec2 readiness ─────────────────────────────────
// Lyrics ALWAYS runs Demucs (backend hardcoded vocal_separation=True).
// Align is optional (controlled by alignEnabled toggle).
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
  if (!await guardModelReady(demucsReady.value, 'audio')) return
  if (alignEnabled.value) {
    if (!await guardModelReady(alignReady.value, 'audio')) return
  }
  if (translationOptions.value?.enableTranslation) {
    const tModel = translationOptions.value.selectedTranslateModel
    const tParsed = parseModelValue(tModel)
    const translateReady = tParsed.isRemote || modelStore.forPanel(modelStore.byCapability('text'))
      .some(m => {
        const [sz, qt] = m.variant.split(':')
        return `${m.family}:${sz}:${qt}` === tModel && m.downloaded
      })
    if (!await guardModelReady(translateReady === true, 'llm')) return
  }
  if (!props.fileId) return

  const body: Record<string, unknown> = {
    file_id: props.fileId,
    model_size: modelSize.value,
    align: alignEnabled.value,
    output_format: outputFormat.value,
    translate: translationOptions.value?.enableTranslation ?? false,
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

  const taskId = await submitTask(
    '/audio/lyrics',
    body,
    t('audio.lyrics.task_label'),
    'audio.lyrics',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

function getParams() {
  const body: Record<string, unknown> = {
    model_size: modelSize.value,
    align: alignEnabled.value,
    output_format: outputFormat.value,
    translate: translationOptions.value?.enableTranslation ?? false,
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

  return body
}

defineExpose({ execute, isDisabled, isLoading, getParams })

onMounted(() => {
  modelStore.fetchModels()
  remoteStore.ensureLoaded()
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-music-note-list me-2"></i>{{ $t('audio.lyrics.title') }}</h6>
    <p class="form-hint">{{ $t('audio.lyrics.description') }}</p>

    <!-- 基本設定 -->
    <div class="form-group">
      <label>{{ $t('audio.lyrics.model') }}</label>
      <AppSelect v-model="modelSize" :options="modelSizes" :placeholder="$t('common.no_models_available')" />
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>

    <!-- Translation (shared component) -->
    <TranslationOptionsPanel ref="translationOptions" :storageKey="'audio_lyrics_translate_model'" />

    <!-- Advanced: align -->
    <SettingsCollapsible storageKey="audio_lyrics_advanced">
      <div class="form-group">
        <AppToggle v-model="alignEnabled">{{ $t('audio.lyrics.align') }}</AppToggle>
        <small class="form-hint">{{ $t('audio.lyrics.align_hint') }}</small>
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
