<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
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

const modelName = ref('htdemucs_6s')
const modelDownloaded = ref<boolean | null>(null)

// Stem toggles
const stemVocals = ref(true)
const stemDrums = ref(true)
const stemBass = ref(true)
const stemGuitar = ref(true)
const stemPiano = ref(true)
const stemOther = ref(true)

const modelOptions = computed(() => [
  { value: 'htdemucs_6s', label: 'HTDemucs 6s (~320 MB)', badge: modelDownloaded.value === null ? null : modelDownloaded.value ? 'ok' as const : 'err' as const },
])

const selectedStems = computed(() => {
  const stems: string[] = []
  if (stemVocals.value) stems.push('vocals')
  if (stemDrums.value) stems.push('drums')
  if (stemBass.value) stems.push('bass')
  if (stemGuitar.value) stems.push('guitar')
  if (stemPiano.value) stems.push('piano')
  if (stemOther.value) stems.push('other')
  return stems
})

async function loadModelStatus() {
  try {
    const res = await apiFetch(`/audio/separate/status?model_name=${modelName.value}`)
    if (!res.ok) return
    const data = await res.json()
    modelDownloaded.value = data.model_downloaded
  } catch {}
}

onMounted(() => { loadModelStatus() })

const isDisabled = computed(() => !props.fileId || isProcessing.value || selectedStems.value.length === 0)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/audio/separate',
    {
      file_id: props.fileId,
      model_name: modelName.value,
      stems: selectedStems.value,
    },
    t('audio.separate.task_label'),
    'audio.separate',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-music-note-list me-2"></i>{{ $t('audio.separate.title') }}</h6>
    <p class="form-hint">{{ $t('audio.separate.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.separate.model') }}</label>
      <AppSelect v-model="modelName" :options="modelOptions" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.separate.stems') }}</label>
      <div class="stem-toggles">
        <AppToggle v-model="stemVocals">{{ $t('audio.separate.stem_vocals') }}</AppToggle>
        <AppToggle v-model="stemDrums">{{ $t('audio.separate.stem_drums') }}</AppToggle>
        <AppToggle v-model="stemBass">{{ $t('audio.separate.stem_bass') }}</AppToggle>
        <AppToggle v-model="stemGuitar">{{ $t('audio.separate.stem_guitar') }}</AppToggle>
        <AppToggle v-model="stemPiano">{{ $t('audio.separate.stem_piano') }}</AppToggle>
        <AppToggle v-model="stemOther">{{ $t('audio.separate.stem_other') }}</AppToggle>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';

.stem-toggles {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
