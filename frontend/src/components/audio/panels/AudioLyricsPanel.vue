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
const showAdvanced = ref(localStorage.getItem('lyrics_advanced') === 'true')
watch(showAdvanced, (v) => localStorage.setItem('lyrics_advanced', String(v)))

const modelSize = usePersistedModel('lyrics_whisper_model', 'medium')
const alignEnabled = ref(false)
const outputFormat = ref('lrc')
const translateEnabled = ref(false)
const targetLanguage = ref('zh-TW')
const selectedTranslateModel = usePersistedModel('lyrics_translate_model')

const outputFormats = computed(() => [
  { value: 'lrc', label: t('audio.lyrics.lrc') },
  { value: 'txt', label: t('audio.lyrics.txt') },
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

watch(localTranslateModelOptions, (options) => {
  if (!selectedTranslateModel.value || !options.some(m => m.value === selectedTranslateModel.value)) {
    const first = options.find(m => m.badge === 'ok')
    selectedTranslateModel.value = first?.value ?? ''
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
// Lyrics ALWAYS runs Demucs (backend hardcoded separate_vocals=True).
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
  if (translateEnabled.value) {
    const tParsed = parseModelValue(selectedTranslateModel.value)
    const translateReady = tParsed.isRemote || localTranslateModelOptions.value.find(m => m.value === selectedTranslateModel.value)?.badge === 'ok'
    if (!await guardModelReady(translateReady === true, 'llm')) return
  }
  if (!props.fileId) return

  const body: Record<string, unknown> = {
    file_id: props.fileId,
    whisper_size: modelSize.value,
    align: alignEnabled.value,
    output_format: outputFormat.value,
    translate: translateEnabled.value,
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
    whisper_size: modelSize.value,
    align: alignEnabled.value,
    output_format: outputFormat.value,
    translate: translateEnabled.value,
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

    <!-- 進階選項（可收合） -->
    <div class="settings-collapsible" :class="{ 'is-open': showAdvanced }">
      <button class="settings-collapsible-header" @click="showAdvanced = !showAdvanced">
        <i class="bi" :class="showAdvanced ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
        <span>{{ $t('common.advanced_options') }}</span>
      </button>

      <div v-if="showAdvanced" class="settings-collapsible-body">
        <div class="form-group">
          <AppToggle v-model="alignEnabled">{{ $t('audio.lyrics.align') }}</AppToggle>
          <small class="form-hint">{{ $t('audio.lyrics.align_hint') }}</small>
        </div>

        <div class="form-group">
          <AppToggle v-model="translateEnabled">{{ $t('audio.lyrics.translate') }}</AppToggle>
          <div v-if="translateEnabled" class="sub-params">
            <div class="form-group">
              <label class="sub-label">{{ $t('audio.lyrics.target_language') }}</label>
              <AppSelect v-model="targetLanguage" :options="translateLanguages" />
            </div>
            <div class="form-group">
              <label class="sub-label">{{ $t('audio.lyrics.translate_model') }}</label>
              <AppSelect v-model="selectedTranslateModel" :options="translateModelOptions" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
