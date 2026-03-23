<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilesStore } from '@/stores/files'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelOptions, parseModelValue } from '@/composables/useModelOptions'
import { apiFetch } from '@/composables/useApi'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  sourceDir?: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const filesStore = useFilesStore()
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()

// ── Whisper model status ────────────────────────────────────────
const whisperAvailable = ref<boolean | null>(null)
const whisperDownloadedMap = ref<Record<string, boolean | null>>({})

const BASE_MODEL_SIZES = [
  { value: 'tiny',     label: 'Tiny (~75 MB)' },
  { value: 'base',     label: 'Base (~145 MB)' },
  { value: 'small',    label: 'Small (~484 MB)' },
  { value: 'medium',   label: 'Medium (~1.5 GB)' },
  { value: 'large-v3', label: 'Large-v3 (~3 GB)' },
]

const modelSizes = computed(() =>
  BASE_MODEL_SIZES.map(m => {
    const dl = whisperDownloadedMap.value[m.value]
    return { ...m, badge: dl === undefined ? null : dl ? 'ok' as const : 'err' as const }
  })
)

async function loadAllModelStatus() {
  await Promise.allSettled(BASE_MODEL_SIZES.map(async ({ value: size }) => {
    try {
      const res = await apiFetch(`/audio/transcribe/status?model_size=${size}`)
      if (!res.ok) return
      const data = await res.json()
      whisperDownloadedMap.value[size] = data.model_downloaded
      if (whisperAvailable.value === null) whisperAvailable.value = data.available
    } catch {}
  }))
}

// ── Settings ────────────────────────────────────────────────────
const showAdvanced = ref(localStorage.getItem('lyrics_advanced') === 'true')
watch(showAdvanced, (v) => localStorage.setItem('lyrics_advanced', String(v)))

const modelSize = ref('medium')
const alignEnabled = ref(false)
const outputFormat = ref('lrc')
const translateEnabled = ref(false)
const targetLanguage = ref('zh-TW')
const selectedTranslateModel = ref('translategemma:4b:Q4_K_M')
const outputPath = ref('')

const outputFormats = computed(() => [
  { value: 'lrc', label: t('audio.lyrics.lrc') },
  { value: 'txt', label: t('audio.lyrics.txt') },
])

// ── Translation model options ───────────────────────────────────
const localTranslateModelOptions = computed(() =>
  modelStore.byCategory('translate')
    .slice()
    .sort((a, b) => a.size_mb - b.size_mb)
    .map(m => {
      const dashIdx = m.variant.indexOf('-')
      const size = m.variant.slice(0, dashIdx)
      const quant = m.variant.slice(dashIdx + 1)
      const key = `${m.family}:${size}:${quant}`
      return { value: key, label: m.label, sizeMb: m.size_mb, badge: m.downloaded ? 'ok' as const : 'err' as const }
    })
)

const { mergedOptions: translateModelOptions } = useModelOptions('text', localTranslateModelOptions)

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
    const res = await apiFetch('/video/translategemma/languages')
    if (res.ok) {
      const data = await res.json()
      translateLanguages.value = data.map((l: { code: string; name: string }) => ({
        value: l.code,
        label: l.name,
      }))
    }
  } catch {}
}

// ── Output path ─────────────────────────────────────────────────
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
      title: t('audio.lyrics.select_output'),
      defaultPath: defaultOutputName.value,
      filters: [{ name: outputFormat.value.toUpperCase(), extensions: [outputFormat.value] }],
    })
    if (result) outputPath.value = result
  }
}

// 切換檔案或格式時，重設為來源目錄的預設路徑
function resetOutputPath() {
  if (props.sourceDir) {
    const stem = props.currentFileName.replace(/\.[^.]+$/, '')
    outputPath.value = `${props.sourceDir}/${stem}.${outputFormat.value}`
  } else {
    outputPath.value = ''
  }
}
watch(() => props.fileId, resetOutputPath)
watch(outputFormat, resetOutputPath)
watch(() => props.sourceDir, resetOutputPath, { immediate: true })
watch(translateEnabled, (val) => { if (val) loadTranslateLanguages() })

// ── Submit ──────────────────────────────────────────────────────
async function execute() {
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
      body.translate_model_type = tmType
      body.translate_model_size = tmSize
      body.translate_quantization = tmQuant
    }
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

defineExpose({ execute, isDisabled, isLoading })

onMounted(() => {
  loadAllModelStatus()
  modelStore.fetchModels()
  remoteStore.fetchAll()
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-music-note-list me-2"></i>{{ $t('audio.lyrics.title') }}</h6>
    <p class="form-hint">{{ $t('audio.lyrics.description') }}</p>

    <div v-if="whisperAvailable === false" class="info-box info-box--warn">
      <i class="bi bi-exclamation-triangle"></i>
      <span>{{ $t('audio.transcribe.not_installed') }}</span>
    </div>

    <!-- 基本設定 -->
    <div class="form-group">
      <label>{{ $t('audio.lyrics.model') }}</label>
      <AppSelect v-model="modelSize" :options="modelSizes" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.lyrics.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.lyrics.output_file') }}</label>
      <div class="file-select" @click="selectOutputFile">
        <span class="file-select-path">{{ displayOutputPath }}</span>
        <i class="bi bi-folder2-open"></i>
      </div>
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
