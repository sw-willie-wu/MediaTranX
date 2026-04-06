<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useMidiEditor } from '@/composables/useMidiEditor'
import { apiFetch } from '@/composables/useApi'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  sourceDir?: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'create-blank': []
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const editor = useMidiEditor()

// ── FluidSynth status ──
const sfReady = ref(false)
apiFetch('/audio/soundfont/info').then(async r => {
  if (r.ok) { sfReady.value = (await r.json()).exists }
})

// ── MIDI file detection ──

const isMidiFile = computed(() => {
  const name = props.currentFileName?.toLowerCase() || ''
  return name.endsWith('.mid') || name.endsWith('.midi')
})

// ── Load MIDI when fileId or fileName changes ──

let _lastLoadedId: string | null = null

watch([() => props.fileId, () => props.currentFileName], async ([id]) => {
  if (id && isMidiFile.value && id !== _lastLoadedId) {
    _lastLoadedId = id
    await editor.loadFromApi(id)
  } else if (!id && isMidiFile.value) {
    // 空白 MIDI（無 fileId）→ 重置 editor
    _lastLoadedId = null
    if (editor.tracks.value.length > 0) {
      editor.tracks.value = []
      editor.selectedNoteIds.value = new Set()
      editor.activeTrackIndex.value = 0
      editor.tempo.value = 120
      editor.timeSignature.value = [4, 4]
      editor.addTrack('Track 1', 0, false)
      editor.isDirty.value = false
    }
  } else if (!isMidiFile.value) {
    _lastLoadedId = null
  }
}, { immediate: true })

// ── Export state ──

const exportFormat = ref('wav')
const exportFormatOptions = [
  { value: 'wav', label: 'WAV' },
  { value: 'mp3', label: 'MP3' },
]

const outputPath = ref('')

const defaultOutputName = computed(() => {
  const stem = props.currentFileName.replace(/\.[^.]+$/, '')
  const ext = exportFormat.value
  return props.sourceDir ? `${props.sourceDir}/${stem}.${ext}` : `${stem}.${ext}`
})

function resetOutputPath() {
  outputPath.value = defaultOutputName.value
}
watch(() => props.fileId, resetOutputPath)
watch(() => props.sourceDir, resetOutputPath, { immediate: true })
watch(exportFormat, resetOutputPath)

async function selectOutputFile() {
  if (window.electron?.saveFileDialog) {
    const ext = exportFormat.value
    const result = await window.electron.saveFileDialog({
      title: t('audio.midi.select_output'),
      defaultPath: outputPath.value || defaultOutputName.value,
      filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
    })
    if (result) outputPath.value = result
  }
}

const displayOutputPath = computed(() => {
  if (!outputPath.value) return defaultOutputName.value
  const p = outputPath.value
  return p.length > 40 ? '...' + p.slice(-37) : p
})

// ── Time signature options ──

const tsNumeratorOptions = Array.from({ length: 12 }, (_, i) => ({
  value: i + 1,
  label: String(i + 1),
}))

const tsDenominatorOptions = [
  { value: 2, label: '2' },
  { value: 4, label: '4' },
  { value: 8, label: '8' },
  { value: 16, label: '16' },
]

// ── Grid options ──

const gridOptions = [
  { value: 1.0, label: '1/4' },
  { value: 0.5, label: '1/8' },
  { value: 0.25, label: '1/16' },
  { value: 0.125, label: '1/32' },
]

// ── Quantize ──

const quantizeResolution = ref(0.25)
const quantizeResolutionOptions = [
  { value: 1.0, label: '1/4' },
  { value: 0.5, label: '1/8' },
  { value: 0.25, label: '1/16' },
  { value: 0.125, label: '1/32' },
]

// ── Tempo (拖動中只更新顯示，放開才寫入) ──

const tempoPreview = ref(120)
watch(() => editor.tempo.value, (v) => { tempoPreview.value = v }, { immediate: true })

function onTempoChange(val: number) {
  editor.tempo.value = val
}

// ── Transpose ──

const transposeSemitones = ref(0)

// ── Time signature helpers ──

const tsNumerator = computed({
  get: () => editor.timeSignature.value[0],
  set: (val: number) => {
    editor.timeSignature.value = [val, editor.timeSignature.value[1]]
  },
})

const tsDenominator = computed({
  get: () => editor.timeSignature.value[1],
  set: (val: number) => {
    editor.timeSignature.value = [editor.timeSignature.value[0], val]
  },
})

// ── Tools（即時套用）──

watch(quantizeResolution, (val) => {
  editor.quantize(val)
})

let _transposeBase = 0  // 記錄拖動開始前的值

function onTransposeChange(val: number) {
  const delta = val - _transposeBase
  if (delta !== 0) {
    editor.transpose(delta)
    _transposeBase = val
  }
}

// ── Execute ──

async function execute() {
  // 彈出儲存對話框讓使用者選路徑
  const ext = exportFormat.value
  const defaultName = (props.currentFileName?.replace(/\.(mid|midi)$/i, '') ?? 'Untitled') + `.${ext}`
  if (window.electron?.saveFileDialog) {
    const filters = ext === 'wav'
      ? [{ name: 'WAV Audio', extensions: ['wav'] }]
      : [{ name: 'MP3 Audio', extensions: ['mp3'] }]
    const savePath = await window.electron.saveFileDialog({
      defaultPath: defaultName,
      filters,
    })
    if (!savePath) return // 使用者取消
    outputPath.value = savePath
  }

  let fileId = props.fileId

  // 空白 MIDI → 先 create 拿 fileId
  if (!fileId) {
    const payload = {
      ticks_per_beat: editor.ticksPerBeat?.value ?? 480,
      tempo: editor.tempo.value,
      time_signature: [...editor.timeSignature.value],
      tracks: editor.tracks.value.map(t => ({
        name: t.name, instrument: t.instrument, color: t.color,
        volume: t.volume, pan: t.pan, muted: t.muted, is_drum: t.isDrum,
        notes: t.notes.map(n => ({
          pitch: n.pitch, start: n.start, duration: n.duration, velocity: n.velocity,
        })),
      })),
    }
    const res = await apiFetch('/audio/midi/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: payload }),
    })
    if (!res.ok) return
    const result = await res.json()
    fileId = result.file_id
  } else {
    // 已有 fileId → save
    await editor.saveToApi(fileId)
  }

  const body: Record<string, string> = {
    file_id: fileId,
    output_format: exportFormat.value,
  }
  if (outputPath.value) {
    body.output_path = outputPath.value.replace(/\\/g, '/')
  }
  const taskId = await submitTask(
    '/audio/midi/export',
    body,
    t('audio.midi.task_label'),
    'audio.midi_export',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

// ── Expose ──

defineExpose({
  execute,
  isDisabled: computed(() => {
    if (!isMidiFile.value || editor.isLoading.value) return true
    // 有 fileId（已存檔的 MIDI）或有音符（空白 MIDI 已編輯）
    if (props.fileId) return false
    return editor.tracks.value.every(t => t.notes.length === 0)
  }),
  isLoading: computed(() => editor.isLoading.value),
  getParams: () => ({ output_format: exportFormat.value }),
  editor,
})
</script>

<template>
  <div class="function-settings">
      <!-- Tool description -->
      <h6 class="settings-title"><i class="bi bi-music-note-list me-2"></i>{{ $t('audio.midi.title') }}</h6>
      <p class="form-hint">{{ $t('audio.midi.description') }}</p>

      <!-- Edit Tools -->
      <div class="form-group">
        <label>{{ $t('audio.midi.edit_tools') }}</label>
        <div class="midi-tool-selector">
          <button
            class="midi-tool-btn"
            :class="{ 'is-active': editor.toolMode.value === 'select' }"
            :data-tooltip="$t('audio.midi.tool_select')"
            @click="editor.toolMode.value = 'select'"
          >
            <i class="bi bi-cursor"></i>
          </button>
          <button
            class="midi-tool-btn"
            :class="{ 'is-active': editor.toolMode.value === 'draw' }"
            :data-tooltip="$t('audio.midi.tool_draw')"
            @click="editor.toolMode.value = 'draw'"
          >
            <i class="bi bi-pencil"></i>
          </button>
          <span class="midi-tool-divider" />
          <button
            class="midi-tool-btn"
            :data-tooltip="$t('audio.midi.new_midi')"
            @click="emit('create-blank')"
          >
            <i class="bi bi-file-earmark-plus"></i>
          </button>
        </div>
      </div>

      <!-- Settings -->
        <!-- Global Settings -->
        <h6 class="settings-title"><i class="bi bi-sliders me-2"></i>{{ $t('audio.midi.global_settings') }}</h6>

        <!-- Tempo -->
        <div class="form-group">
          <label>
            {{ $t('audio.midi.tempo') }}
            <span class="param-value">{{ tempoPreview }}</span>
          </label>
          <AppRange
            v-model="tempoPreview"
            :min="20"
            :max="300"
            @change="onTempoChange"
          />
        </div>

        <!-- Time Signature -->
        <div class="form-group">
          <label>{{ $t('audio.midi.time_signature') }}</label>
          <div class="midi-time-sig">
            <AppSelect v-model="tsNumerator" :options="tsNumeratorOptions" size="sm" />
            <span class="midi-time-sig-sep">/</span>
            <AppSelect v-model="tsDenominator" :options="tsDenominatorOptions" size="sm" />
          </div>
        </div>

        <!-- Grid -->
        <div class="form-group">
          <label>{{ $t('audio.midi.grid') }}</label>
          <AppSelect v-model="editor.gridSize.value" :options="gridOptions" />
        </div>

        <!-- Snap -->
        <div class="form-group">
          <label>{{ $t('audio.midi.snap') }}</label>
          <AppToggle v-model="editor.snapEnabled.value">{{ $t('audio.midi.snap') }}</AppToggle>
        </div>

        <!-- Tools -->
        <h6 class="settings-title"><i class="bi bi-tools me-2"></i>{{ $t('audio.midi.tools') }}</h6>

        <!-- Quantize -->
        <div class="form-group">
          <label>{{ $t('audio.midi.quantize') }}</label>
          <AppSelect v-model="quantizeResolution" :options="quantizeResolutionOptions" />
        </div>

        <!-- Transpose -->
        <div class="form-group">
          <label>
            {{ $t('audio.midi.transpose') }}
            <span class="param-value">{{ transposeSemitones > 0 ? '+' : '' }}{{ transposeSemitones }}</span>
          </label>
          <AppRange
            v-model="transposeSemitones"
            :min="-24"
            :max="24"
            @change="onTransposeChange"
          />
        </div>

      <!-- Export -->
      <h6 class="settings-title"><i class="bi bi-download me-2"></i>{{ $t('audio.midi.export') }}</h6>

      <div class="form-group">
        <label>{{ $t('audio.midi.export_format') }}</label>
        <AppSelect v-model="exportFormat" :options="exportFormatOptions" />
      </div>

      <div class="form-group">
        <label>{{ $t('audio.midi.output_path') }}</label>
        <div class="file-select" @click="selectOutputFile">
          <span class="file-select-path">{{ displayOutputPath }}</span>
          <i class="bi bi-folder2-open"></i>
        </div>
      </div>

      <div v-if="exportFormat !== 'mid' && !sfReady" class="info-box info-box--info">
        <i class="bi bi-info-circle"></i>
        {{ $t('audio.midi.soundfont_missing') }}
      </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';


.midi-tool-selector {
  display: flex;
  align-items: center;
  gap: 4px;
}

.midi-tool-divider {
  width: 1px;
  height: 20px;
  background: var(--input-border);
  margin: 0 2px;
}

.midi-tool-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    border-color: var(--panel-border-hover);
    color: var(--text-primary);
  }

  &.is-active {
    background: rgba(168, 156, 200, 0.15);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }

  i { font-size: 1rem; }

  &::after {
    content: attr(data-tooltip);
    position: absolute;
    top: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    padding: 3px 8px;
    background: var(--panel-bg-active);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.72rem;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s ease;
    z-index: 10;
  }

  &:hover::after { opacity: 1; }
}

.midi-time-sig {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.midi-time-sig-sep {
  font-size: 1rem;
  color: var(--text-muted);
  font-weight: 600;
}

</style>
