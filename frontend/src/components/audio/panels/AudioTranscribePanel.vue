<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { apiFetch } from '@/composables/useApi'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const modelSize = ref('medium')
const language = ref('')
const outputFormat = ref('txt')
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

onMounted(() => { loadAllModelStatus(); loadLanguages() })

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/audio/transcribe',
    {
      file_id: props.fileId,
      language: language.value || null,
      model_size: modelSize.value,
      output_format: outputFormat.value,
    },
    t('audio.transcribe.task_label'),
    'audio.transcribe',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-mic-fill me-2"></i>{{ $t('audio.transcribe.title') }}</h6>
    <p class="form-hint">{{ $t('audio.transcribe.description') }}</p>

    <div v-if="whisperAvailable === false" class="info-box info-box--warn">
      <i class="bi bi-exclamation-triangle"></i>
      <span>{{ $t('audio.transcribe.not_installed') }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('audio.transcribe.model') }}</label>
      <AppSelect v-model="modelSize" :options="modelSizes" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.transcribe.language') }}</label>
      <AppSelect v-model="language" :options="languages" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.transcribe.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
      <small class="form-hint">
        {{ outputFormat === 'srt' ? $t('audio.transcribe.srt_hint') : $t('audio.transcribe.txt_hint') }}
      </small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

