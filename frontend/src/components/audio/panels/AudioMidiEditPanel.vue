<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useMidiEditor } from '@/composables/useMidiEditor'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const editor = useMidiEditor()

// ── MIDI file detection ──

const isMidiFile = computed(() => {
  const name = props.currentFileName?.toLowerCase() || ''
  return name.endsWith('.mid') || name.endsWith('.midi')
})

// ── Load MIDI when fileId changes ──

watch(() => props.fileId, async (id) => {
  if (id && isMidiFile.value) {
    await editor.loadFromApi(id)
  }
}, { immediate: true })

// ── Export state ──

const exportFormat = ref('mid')
const exportFormatOptions = [
  { value: 'mid', label: 'MIDI' },
  { value: 'wav', label: 'WAV' },
  { value: 'mp3', label: 'MP3' },
]

// ── GM Instrument options ──

const instrumentOptions = [
  { value: 0, label: 'Acoustic Grand Piano' },
  { value: 4, label: 'Electric Piano 1' },
  { value: 6, label: 'Harpsichord' },
  { value: 13, label: 'Xylophone' },
  { value: 24, label: 'Acoustic Guitar (nylon)' },
  { value: 25, label: 'Acoustic Guitar (steel)' },
  { value: 26, label: 'Electric Guitar (jazz)' },
  { value: 30, label: 'Distortion Guitar' },
  { value: 33, label: 'Electric Bass (finger)' },
  { value: 34, label: 'Electric Bass (pick)' },
  { value: 40, label: 'Violin' },
  { value: 42, label: 'Cello' },
  { value: 48, label: 'String Ensemble 1' },
  { value: 52, label: 'Choir Aahs' },
  { value: 56, label: 'Trumpet' },
  { value: 57, label: 'Trombone' },
  { value: 61, label: 'French Horn' },
  { value: 65, label: 'Alto Sax' },
  { value: 73, label: 'Flute' },
  { value: 74, label: 'Recorder' },
  { value: 80, label: 'Synth Lead (square)' },
  { value: 81, label: 'Synth Lead (sawtooth)' },
  { value: 88, label: 'Synth Pad (new age)' },
]

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

// ── Transpose ──

const transposeSemitones = ref(0)

// ── Track helpers ──

function getInstrumentOptions(trackIndex: number) {
  return instrumentOptions.map(opt => ({
    ...opt,
    value: opt.value,
  }))
}

function onInstrumentChange(trackIndex: number, value: number) {
  editor.updateTrack(trackIndex, { instrument: value })
}

function onTrackNameInput(trackIndex: number, event: Event) {
  const target = event.target as HTMLInputElement
  editor.updateTrack(trackIndex, { name: target.value })
}

function onVolumeChange(trackIndex: number, value: number) {
  editor.updateTrack(trackIndex, { volume: value })
}

function onPanChange(trackIndex: number, value: number) {
  editor.updateTrack(trackIndex, { pan: value })
}

function toggleMute(trackIndex: number) {
  const track = editor.tracks.value[trackIndex]
  if (track) {
    editor.updateTrack(trackIndex, { muted: !track.muted })
  }
}

function toggleSolo(trackIndex: number) {
  // Solo: mute all other tracks, unmute this one
  const tracks = editor.tracks.value
  const isAlreadySolo = tracks.every((t, i) =>
    i === trackIndex ? !t.muted : t.muted,
  )
  if (isAlreadySolo) {
    // Un-solo: unmute all
    for (let i = 0; i < tracks.length; i++) {
      editor.updateTrack(i, { muted: false })
    }
  } else {
    for (let i = 0; i < tracks.length; i++) {
      editor.updateTrack(i, { muted: i !== trackIndex })
    }
  }
}

function onAddTrack() {
  editor.addTrack()
}

function onDeleteTrack() {
  if (editor.tracks.value.length <= 1) return
  editor.deleteTrack(editor.activeTrackIndex.value)
}

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

// ── Tools ──

function applyQuantize() {
  editor.quantize(quantizeResolution.value)
}

function applyTranspose() {
  if (transposeSemitones.value !== 0) {
    editor.transpose(transposeSemitones.value)
  }
}

// ── Execute ──

async function execute() {
  if (!props.fileId) return
  // Save current state first
  await editor.saveToApi(props.fileId)
  // Just save for MIDI format, no export task needed
  if (exportFormat.value === 'mid') {
    return
  }
  const taskId = await submitTask(
    '/audio/midi/export',
    { file_id: props.fileId, output_format: exportFormat.value },
    t('audio.midi.task_label'),
    'audio.midi_export',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

// ── Expose ──

defineExpose({
  execute,
  isDisabled: computed(() => !props.fileId || !isMidiFile.value || editor.isLoading.value),
  isLoading: computed(() => editor.isLoading.value),
  getParams: () => ({ output_format: exportFormat.value }),
  editor,
})
</script>

<template>
  <div class="function-settings">
    <!-- Not a MIDI file -->
    <template v-if="!isMidiFile">
      <div class="info-box info-box--info">
        <i class="bi bi-info-circle"></i>
        {{ $t('audio.midi.unsupported') }}
      </div>
    </template>

    <!-- MIDI editor settings -->
    <template v-else>
      <!-- Section 1: Track Management -->
      <h6 class="settings-title"><i class="bi bi-music-note-list me-2"></i>{{ $t('audio.midi.tracks') }}</h6>

      <div
        v-for="(track, idx) in editor.tracks.value"
        :key="idx"
        class="midi-track-row"
        :class="{ 'midi-track-row--active': idx === editor.activeTrackIndex.value }"
        @click="editor.activeTrackIndex.value = idx"
      >
        <!-- Track header: color dot + name + instrument -->
        <div class="midi-track-header">
          <span class="midi-track-color" :style="{ backgroundColor: track.color }"></span>
          <input
            class="form-input midi-track-name"
            :value="track.name"
            @input="onTrackNameInput(idx, $event)"
            @click.stop
          />
          <button
            class="midi-track-btn"
            :class="{ 'midi-track-btn--active': track.muted }"
            :title="$t('audio.midi.mute')"
            @click.stop="toggleMute(idx)"
          >
            <i class="bi bi-volume-mute-fill"></i>
          </button>
          <button
            class="midi-track-btn"
            :title="$t('audio.midi.solo')"
            @click.stop="toggleSolo(idx)"
          >
            <i class="bi bi-headphones"></i>
          </button>
        </div>

        <!-- Instrument select -->
        <div class="form-group midi-track-param">
          <label>{{ $t('audio.midi.instrument') }}</label>
          <AppSelect
            :model-value="track.instrument"
            :options="getInstrumentOptions(idx)"
            size="sm"
            @update:model-value="onInstrumentChange(idx, $event)"
          />
        </div>

        <!-- Volume -->
        <div class="form-group midi-track-param">
          <label>
            {{ $t('audio.midi.volume') }}
            <span class="param-value">{{ track.volume }}</span>
          </label>
          <AppRange
            :model-value="track.volume"
            :min="0"
            :max="127"
            @update:model-value="onVolumeChange(idx, $event)"
          />
        </div>

        <!-- Pan -->
        <div class="form-group midi-track-param">
          <label>
            {{ $t('audio.midi.pan') }}
            <span class="param-value">{{ track.pan }}<template v-if="track.pan === 64"> (C)</template></span>
          </label>
          <AppRange
            :model-value="track.pan"
            :min="0"
            :max="127"
            @update:model-value="onPanChange(idx, $event)"
          />
          <div class="range-ticks">
            <span>L</span>
            <span>C</span>
            <span>R</span>
          </div>
        </div>
      </div>

      <!-- Add / Delete Track buttons -->
      <div class="midi-track-actions">
        <button class="btn-secondary" @click="onAddTrack">
          <i class="bi bi-plus"></i>
          {{ $t('audio.midi.add_track') }}
        </button>
        <button
          class="btn-secondary"
          :disabled="editor.tracks.value.length <= 1"
          @click="onDeleteTrack"
        >
          <i class="bi bi-trash"></i>
          {{ $t('audio.midi.delete_track') }}
        </button>
      </div>

      <!-- Section 2: Global Settings -->
      <h6 class="settings-title"><i class="bi bi-gear me-2"></i>{{ $t('audio.midi.title') }}</h6>

      <!-- Tempo -->
      <div class="form-group">
        <label>{{ $t('audio.midi.tempo') }}</label>
        <input
          v-model.number="editor.tempo.value"
          type="number"
          class="form-input"
          min="20"
          max="300"
          step="1"
        />
        <span class="form-hint">BPM</span>
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
        <AppToggle v-model="editor.snapEnabled.value">{{ $t('audio.midi.snap_enabled') }}</AppToggle>
      </div>

      <!-- Section 3: Tools -->
      <h6 class="settings-title"><i class="bi bi-tools me-2"></i>{{ $t('audio.midi.tools') }}</h6>

      <!-- Quantize -->
      <div class="form-group">
        <label>{{ $t('audio.midi.quantize') }}</label>
        <div class="midi-tool-row">
          <AppSelect v-model="quantizeResolution" :options="quantizeResolutionOptions" size="sm" />
          <button class="btn-secondary" @click="applyQuantize">
            {{ $t('audio.midi.apply') }}
          </button>
        </div>
        <span class="form-hint">{{ $t('audio.midi.quantize_hint') }}</span>
      </div>

      <!-- Transpose -->
      <div class="form-group">
        <label>{{ $t('audio.midi.transpose') }}</label>
        <div class="midi-tool-row">
          <input
            v-model.number="transposeSemitones"
            type="number"
            class="form-input"
            min="-48"
            max="48"
            step="1"
          />
          <button class="btn-secondary" @click="applyTranspose">
            {{ $t('audio.midi.apply') }}
          </button>
        </div>
        <span class="form-hint">{{ $t('audio.midi.transpose_hint') }}</span>
      </div>

      <!-- Section 4: Export -->
      <h6 class="settings-title"><i class="bi bi-download me-2"></i>{{ $t('audio.midi.export') }}</h6>

      <div class="form-group">
        <label>{{ $t('audio.midi.export_format') }}</label>
        <AppSelect v-model="exportFormat" :options="exportFormatOptions" />
      </div>

      <div v-if="exportFormat !== 'mid'" class="info-box info-box--info">
        <i class="bi bi-info-circle"></i>
        {{ $t('audio.midi.soundfont_info') }}
      </div>
    </template>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';

.midi-track-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.65rem 0.75rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;

  &:hover {
    border-color: var(--panel-border-hover);
  }

  &--active {
    border-color: var(--color-primary);
    background: rgba(124, 111, 173, 0.06);
  }
}

.midi-track-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.midi-track-color {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.midi-track-name {
  flex: 1;
  padding: 0.25rem 0.5rem !important;
  font-size: 0.82rem !important;
  min-width: 0;
}

.midi-track-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 0.8rem;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  &--active {
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.3);
    color: #ef4444;
  }
}

.midi-track-param {
  gap: 0.25rem !important;

  label {
    font-size: 0.75rem !important;
  }
}

.midi-track-actions {
  display: flex;
  gap: 0.5rem;

  .btn-secondary {
    flex: 1;
  }
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

.midi-tool-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;

  .form-input,
  .app-select-trigger {
    flex: 1;
  }

  .btn-secondary {
    width: auto;
    flex-shrink: 0;
    white-space: nowrap;
  }
}
</style>
