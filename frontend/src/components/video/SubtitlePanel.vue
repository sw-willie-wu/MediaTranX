<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import AppSelect from '@/components/common/AppSelect.vue'
import WhisperAdvancedSettings from '@/components/video/WhisperAdvancedSettings.vue'
import TranslationOptionsPanel from '@/components/video/TranslationOptionsPanel.vue'
import { apiFetch, getApiBase } from '@/composables/useApi'
import { parseModelValue } from '@/composables/useModelOptions'
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import { useSettingsStore } from '@/stores/settings'

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
  sourceDir?: string
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
const settingsStore = useSettingsStore()

const isLoading = ref(false)
const error = ref<string | null>(null)

// ── Whisper 模型狀態 ────────────────────────────────────────────
const whisperAvailable = ref<boolean | null>(null)
const whisperDownloadedMap = ref<Record<string, boolean | null>>({})

const baseModelSizes = [
  { value: 'tiny',     label: 'Tiny (~75 MB)' },
  { value: 'base',     label: 'Base (~145 MB)' },
  { value: 'small',    label: 'Small (~484 MB)' },
  { value: 'medium',   label: 'Medium (~1.5 GB)' },
  { value: 'large-v3', label: 'Large-v3 (~3 GB)' },
]

const modelSizesWithBadge = computed(() => {
  const all = baseModelSizes.map(m => {
    const dl = whisperDownloadedMap.value[m.value]
    return { ...m, badge: dl === undefined ? null : dl ? 'ok' as const : 'err' as const }
  })
  return settingsStore.showAllModels ? all : all.filter(m => m.badge === 'ok')
})

async function loadAllWhisperStatus() {
  await Promise.allSettled(baseModelSizes.map(async ({ value: size }) => {
    try {
      const res = await fetch(`${getApiBase()}/video/whisper/status?model_size=${size}`)
      if (!res.ok) return
      const data = await res.json()
      whisperDownloadedMap.value[size] = data.model_downloaded
      if (whisperAvailable.value === null) whisperAvailable.value = data.available
    } catch {}
  }))
}

watch(() => modelStore.version, () => loadAllWhisperStatus())

// Auto-reselect when filtered list no longer contains current selection
watch(modelSizesWithBadge, (sizes) => {
  if (sizes.length > 0 && !sizes.some(m => m.value === modelSize.value)) {
    modelSize.value = sizes[0].value
  }
})

// ── 字幕選項 ────────────────────────────────────────────────────
const language = ref('')
const modelSize = ref('medium')
const outputFormat = ref('srt')
const outputPath = ref('')

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

const showAdvanced = ref(localStorage.getItem('subtitle_advanced') === 'true')
watch(showAdvanced, (v) => localStorage.setItem('subtitle_advanced', String(v)))

const outputFormats = computed(() => [
  { value: 'srt', label: t('video.subtitle.srt') },
  { value: 'vtt', label: t('video.subtitle.vtt') },
])

// ── 輸出路徑 ────────────────────────────────────────────────────
const sourceBaseName = computed(() => {
  const file = filesStore.currentFile
  if (!file?.originalName) return 'output'
  const name = file.originalName
  const lastDot = name.lastIndexOf('.')
  return lastDot > 0 ? name.substring(0, lastDot) : name
})

const defaultOutputName = computed(() => `${sourceBaseName.value}.${outputFormat.value}`)

const displayOutputPath = computed(() => {
  if (outputPath.value) {
    const parts = outputPath.value.replace(/\\/g, '/').split('/')
    return parts[parts.length - 1]
  }
  return defaultOutputName.value
})

async function selectOutputFile() {
  if (window.electron?.saveFileDialog) {
    const result = await window.electron.saveFileDialog({
      title: t('video.subtitle.select_output'),
      defaultPath: defaultOutputName.value,
      filters: [{ name: t('video.subtitle.file_type'), extensions: [outputFormat.value] }],
    })
    if (result) outputPath.value = result
  }
}

function resetOutputPath() {
  if (props.sourceDir) {
    const stem = sourceBaseName.value
    outputPath.value = `${props.sourceDir}/${stem}.${outputFormat.value}`
  } else {
    outputPath.value = ''
  }
}
watch(() => props.fileId, resetOutputPath)
watch(outputFormat, resetOutputPath)
watch(() => props.sourceDir, resetOutputPath, { immediate: true })

// ── 子元件 refs ─────────────────────────────────────────────────
const whisperAdvanced = ref<InstanceType<typeof WhisperAdvancedSettings> | null>(null)
const translationOptions = ref<InstanceType<typeof TranslationOptionsPanel> | null>(null)

// ── 提交 ────────────────────────────────────────────────────────
async function submitGenerate() {
  if (!await guardModelReady(whisperDownloadedMap.value[modelSize.value] === true, 'audio')) return
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
    const body: Record<string, any> = {
      file_id: props.fileId,
      model_size: modelSize.value,
      output_format: outputFormat.value,
    }

    if (language.value) body.language = language.value

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
        body.translate_model_type = tmType
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

    if (outputPath.value) {
      const path = outputPath.value.replace(/\\/g, '/')
      const lastSlash = path.lastIndexOf('/')
      if (lastSlash > 0) {
        body.output_dir = path.substring(0, lastSlash)
        body.output_filename = path.substring(lastSlash + 1)
      } else {
        body.output_filename = path
      }
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
  isLoading.value || !props.fileId || whisperAvailable.value === false
)

defineExpose({ submitGenerate, isLoading, isDisabled })

onMounted(() => { loadAllWhisperStatus(); loadLanguages(); modelStore.ensureLoaded() })
</script>

<template>
  <div class="function-settings">
    <div v-if="error" class="info-box info-box--error">
      <i class="bi bi-exclamation-circle"></i>
      <span>{{ error }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('video.subtitle.language') }}</label>
      <AppSelect v-model="language" :options="languages" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.subtitle.model_settings') }}</label>
      <AppSelect v-model="modelSize" :options="modelSizesWithBadge" :placeholder="$t('common.no_models_available')" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.subtitle.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.subtitle.file_type') }}</label>
      <div class="file-select" @click="selectOutputFile">
        <span class="file-select-path">{{ displayOutputPath }}</span>
        <i class="bi bi-folder2-open"></i>
      </div>
    </div>

    <!-- Advanced options (collapsible) -->
    <div class="settings-collapsible" :class="{ 'is-open': showAdvanced }">
      <button class="settings-collapsible-header" @click="showAdvanced = !showAdvanced">
        <i class="bi" :class="showAdvanced ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
        <span>{{ $t('common.advanced_options') }}</span>
      </button>

      <div v-show="showAdvanced" class="settings-collapsible-body">
        <WhisperAdvancedSettings ref="whisperAdvanced" />
        <TranslationOptionsPanel ref="translationOptions" />
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
