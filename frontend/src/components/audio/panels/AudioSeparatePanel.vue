<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { apiFetch } from '@/composables/useApi'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  sourceDir?: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'jump-to-midi': [fileId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const modelName = ref('htdemucs_6s')
const modelDownloaded = ref<boolean | null>(null)
const outputFormat = ref('wav')
const outputPath = ref('')

const outputFormats = computed(() => [
  { value: 'wav', label: 'WAV' },
  { value: 'flac', label: 'FLAC' },
  { value: 'mp3', label: 'MP3' },
])

// Output path
const defaultOutputName = computed(() => {
  const stem = props.currentFileName.replace(/\.[^.]+$/, '')
  return `${stem}.vocals.${outputFormat.value}`
})

const displayOutputPath = computed(() => {
  if (outputPath.value) {
    const parts = outputPath.value.replace(/\\/g, '/').split('/').filter(Boolean)
    const dir = parts.length > 2 ? `.../${parts.slice(-2).join('/')}` : outputPath.value
    return `${dir}/${defaultOutputName.value}`
  }
  return defaultOutputName.value
})

async function selectOutputFile() {
  if (window.electron?.openDirectoryDialog) {
    const result = await window.electron.openDirectoryDialog({
      title: t('audio.separate.select_output'),
    })
    if (result) outputPath.value = result
  }
}

function resetOutputPath() {
  if (props.sourceDir) {
    outputPath.value = props.sourceDir
  } else {
    outputPath.value = ''
  }
}
watch(() => props.fileId, resetOutputPath)
watch(() => props.sourceDir, resetOutputPath, { immediate: true })

// MIDI output
const generateMidi = ref(false)
const showJumpModal = ref(false)
const midiFileId = ref<string | null>(null)

// Stem toggles
const stemVocals = ref(true)
const stemDrums = ref(true)
const stemBass = ref(true)
const stemGuitar = ref(true)
const stemPiano = ref(true)
const stemOther = ref(true)

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
  const body: Record<string, unknown> = {
    file_id: props.fileId,
    model_name: modelName.value,
    stems: selectedStems.value,
    output_format: outputFormat.value,
    generate_midi: generateMidi.value,
  }
  if (outputPath.value) {
    body.output_dir = outputPath.value.replace(/\\/g, '/')
  }
  const taskId = await submitTask(
    '/audio/separate',
    body,
    t('audio.separate.task_label'),
    'audio.separate',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

function getParams() {
  const body: Record<string, unknown> = {
    model_name: modelName.value,
    stems: selectedStems.value,
    output_format: outputFormat.value,
    generate_midi: generateMidi.value,
  }
  if (outputPath.value) {
    body.output_dir = outputPath.value.replace(/\\/g, '/')
  }
  return body
}

function handleJumpToMidi() {
  showJumpModal.value = false
  if (midiFileId.value) {
    emit('jump-to-midi', midiFileId.value)
  }
}

function onTaskComplete(result: Record<string, unknown>) {
  if (result.midi_file_id) {
    midiFileId.value = result.midi_file_id as string
    showJumpModal.value = true
  }
}

defineExpose({ execute, isDisabled, isLoading, getParams, onTaskComplete })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-music-note-list me-2"></i>{{ $t('audio.separate.title') }}</h6>
    <p class="form-hint">{{ $t('audio.separate.description') }}</p>

    <div v-if="modelDownloaded === false" class="info-box info-box--warn">
      <i class="bi bi-exclamation-triangle"></i>
      <span>{{ $t('audio.separate.model_not_downloaded') }}</span>
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

    <div class="form-group">
      <label>{{ $t('audio.separate.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.separate.generate_midi') }}</label>
      <AppToggle v-model="generateMidi">
        {{ $t('audio.separate.generate_midi_desc') }}
      </AppToggle>
    </div>

    <div class="form-group">
      <label>{{ $t('audio.separate.output_file') }}</label>
      <div class="file-select" @click="selectOutputFile">
        <span class="file-select-path">{{ displayOutputPath }}</span>
        <i class="bi bi-folder2-open"></i>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <div v-if="showJumpModal" class="modal-overlay" @click.self="showJumpModal = false">
      <div class="modal-dialog">
        <div class="modal-body">
          <i class="bi bi-music-note-beamed modal-icon"></i>
          <p>{{ $t('audio.separate.midi_jump_prompt') }}</p>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showJumpModal = false">
            {{ $t('audio.separate.midi_stay') }}
          </button>
          <button class="btn-primary" @click="handleJumpToMidi">
            {{ $t('audio.separate.midi_jump') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style lang="scss" scoped>
@use '@/styles/tool-panels-shared';

.stem-toggles {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.modal-dialog {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 24px;
  max-width: 400px;
  width: 90%;
}
.modal-body {
  text-align: center;
  margin-bottom: 20px;
}
.modal-icon {
  font-size: 32px;
  color: var(--color-primary);
  margin-bottom: 12px;
  display: block;
}
.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
