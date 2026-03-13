<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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

const { submitTask, isProcessing } = useSubmitTask()

const modelSize = ref('medium')
const language = ref('')
const outputFormat = ref('txt')
const whisperAvailable = ref<boolean | null>(null)
const whisperDownloadedMap = ref<Record<string, boolean | null>>({})

const BASE_MODEL_SIZES = [
  { value: 'tiny',     label: 'Tiny',     desc: '~75 MB — 最快' },
  { value: 'base',     label: 'Base',     desc: '~145 MB' },
  { value: 'small',    label: 'Small',    desc: '~484 MB' },
  { value: 'medium',   label: 'Medium',   desc: '~1.5 GB — 推薦' },
  { value: 'large-v3', label: 'Large-v3', desc: '~3 GB — 最佳' },
]

const modelSizes = computed(() =>
  BASE_MODEL_SIZES.map(m => {
    const dl = whisperDownloadedMap.value[m.value]
    return { ...m, badge: dl === undefined ? null : dl ? 'ok' as const : 'err' as const }
  })
)

const languages = ref<{ value: string; label: string }[]>([])

async function loadLanguages() {
  try {
    const res = await apiFetch('/audio/transcribe/languages')
    if (res.ok) languages.value = await res.json()
  } catch {}
}

const outputFormats = [
  { value: 'txt', label: 'TXT（純文字）' },
  { value: 'srt', label: 'SRT（含時間碼）' },
]

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
    '逐字稿轉譯',
    'audio.transcribe',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-mic-fill me-2"></i>逐字稿設定</h6>
    <p class="form-hint">使用 Whisper 將音訊內容轉為文字或 SRT 字幕檔。</p>

    <div v-if="whisperAvailable === false" class="info-box info-box--warn">
      <i class="bi bi-exclamation-triangle"></i>
      <span>AI 核心環境未安裝，請先至設定頁面安裝。</span>
    </div>

    <div class="form-group">
      <label>辨識模型</label>
      <AppSelect v-model="modelSize" :options="modelSizes" />
    </div>

    <div class="form-group">
      <label>語言</label>
      <AppSelect v-model="language" :options="languages" />
    </div>

    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
      <small class="form-hint">
        {{ outputFormat === 'srt' ? '輸出含時間碼的 SRT 字幕格式' : '輸出純文字逐字稿' }}
      </small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

