<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'
import { useMidiEditor } from '@/composables/useMidiEditor'
import { apiFetch } from '@/composables/useApi'
import { useToneSynth, effectsState } from '@/composables/useToneSynth'
import { useMidiExport } from '@/composables/useMidiExport'
import MidiExportParams from '@/components/params/audio/MidiExportParams.vue'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'create-blank': []
}>()

const { t } = useI18n()
const editor = useMidiEditor()
const synth = useToneSynth()
const midiExport = useMidiExport()

// ── Tab state ──
const activeTab = ref<'edit' | 'effects' | 'export'>('edit')
// `as const` so `tab.id` keeps its literal type for `activeTab` assignment
// (an inline template array widens it to `string`). labelKey resolves via t()
// in the template, keeping locale reactivity.
const tabs = [
  { id: 'edit', labelKey: 'audio.midi.tab_edit' },
  { id: 'effects', labelKey: 'audio.midi.tab_effects' },
  { id: 'export', labelKey: 'audio.midi.tab_export' },
] as const

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
// exportFormat 是 getParams()/execute() 的唯一事實來源（不動——見檔頭邊界鐵則）；
// exportFormatOptions 已搬進 MidiExportParams.vue（批 3 Task 3.5 Part B，最小侵入拆分），
// exportParamsModel 是 Export tab 掛載 MidiExportParams 用的受控 v-model 轉接器。

const exportFormat = ref('wav')

const exportParamsModel = computed({
  get: () => ({ output_format: exportFormat.value }),
  set: (v: Record<string, unknown>) => { exportFormat.value = String(v.output_format ?? 'wav') },
})

const defaultBaseName = computed(() => {
  return props.currentFileName?.replace(/\.[^.]+$/, '') || 'Untitled'
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

  const taskId = midiExport.exportMidi(
    editor.tracks.value,
    editor.tempo.value,
    exportFormat.value,
    defaultBaseName.value,
    fileId ?? undefined,
  )
  emit('submit', taskId)
}

// ── Expose ──

defineExpose({
  execute,
  isDisabled: computed(() => {
    if (!isMidiFile.value || editor.isLoading.value || midiExport.isExporting.value) return true
    // 有 fileId（已存檔的 MIDI）或有音符（空白 MIDI 已編輯）
    if (props.fileId) return false
    return editor.tracks.value.every(t => t.notes.length === 0)
  }),
  isLoading: computed(() => editor.isLoading.value || midiExport.isExporting.value),
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

      <!-- Tab navigation -->
      <div class="settings-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="settings-tab"
          :class="{ 'is-active': activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ t(tab.labelKey) }}
        </button>
      </div>

      <!-- Edit tab -->
      <div v-show="activeTab === 'edit'" class="function-settings">
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
            <AppSelect v-model="tsNumerator" :options="tsNumeratorOptions" />
            <span class="midi-time-sig-sep">/</span>
            <AppSelect v-model="tsDenominator" :options="tsDenominatorOptions" />
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
      </div>

      <!-- Effects tab -->
      <div v-show="activeTab === 'effects'" class="function-settings">
        <div class="settings-title">EQ</div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_eq_low') }}</label>
          <AppRange :model-value="effectsState.eq.low" @update:model-value="synth.updateEffects({ eq: { low: $event } })" :min="-12" :max="12" :step="0.5" />
          <span class="form-hint">{{ effectsState.eq.low.toFixed(1) }} dB</span>
        </div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_eq_mid') }}</label>
          <AppRange :model-value="effectsState.eq.mid" @update:model-value="synth.updateEffects({ eq: { mid: $event } })" :min="-12" :max="12" :step="0.5" />
          <span class="form-hint">{{ effectsState.eq.mid.toFixed(1) }} dB</span>
        </div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_eq_high') }}</label>
          <AppRange :model-value="effectsState.eq.high" @update:model-value="synth.updateEffects({ eq: { high: $event } })" :min="-12" :max="12" :step="0.5" />
          <span class="form-hint">{{ effectsState.eq.high.toFixed(1) }} dB</span>
        </div>

        <div class="settings-title">{{ t('audio.midi.effects_compressor') }}</div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_threshold') }}</label>
          <AppRange :model-value="effectsState.compressor.threshold" @update:model-value="synth.updateEffects({ compressor: { threshold: $event } })" :min="-60" :max="0" :step="1" />
          <span class="form-hint">{{ effectsState.compressor.threshold }} dB</span>
        </div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_ratio') }}</label>
          <AppRange :model-value="effectsState.compressor.ratio" @update:model-value="synth.updateEffects({ compressor: { ratio: $event } })" :min="1" :max="20" :step="0.5" />
          <span class="form-hint">{{ effectsState.compressor.ratio.toFixed(1) }}:1</span>
        </div>

        <div class="settings-title">{{ t('audio.midi.effects_delay') }}</div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_delay_time') }}</label>
          <AppRange :model-value="effectsState.delay.time" @update:model-value="synth.updateEffects({ delay: { time: $event } })" :min="0" :max="1" :step="0.01" />
          <span class="form-hint">{{ (effectsState.delay.time * 1000).toFixed(0) }} ms</span>
        </div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_delay_feedback') }}</label>
          <AppRange :model-value="effectsState.delay.feedback" @update:model-value="synth.updateEffects({ delay: { feedback: $event } })" :min="0" :max="0.9" :step="0.01" />
          <span class="form-hint">{{ (effectsState.delay.feedback * 100).toFixed(0) }}%</span>
        </div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_delay_wet') }}</label>
          <AppRange :model-value="effectsState.delay.wet" @update:model-value="synth.updateEffects({ delay: { wet: $event } })" :min="0" :max="1" :step="0.01" />
          <span class="form-hint">{{ (effectsState.delay.wet * 100).toFixed(0) }}%</span>
        </div>

        <div class="settings-title">{{ t('audio.midi.effects_reverb') }}</div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_reverb_decay') }}</label>
          <AppRange :model-value="effectsState.reverb.decay" @update:model-value="synth.updateEffects({ reverb: { decay: $event } })" :min="0.1" :max="10" :step="0.1" />
          <span class="form-hint">{{ effectsState.reverb.decay.toFixed(1) }} s</span>
        </div>
        <div class="form-group">
          <label>{{ t('audio.midi.effects_reverb_wet') }}</label>
          <AppRange :model-value="effectsState.reverb.wet" @update:model-value="synth.updateEffects({ reverb: { wet: $event } })" :min="0" :max="1" :step="0.01" />
          <span class="form-hint">{{ (effectsState.reverb.wet * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <!-- Export tab -->
      <div v-show="activeTab === 'export'" class="function-settings">
        <MidiExportParams v-model:params="exportParamsModel" context="tool" />
        <p class="form-hint">{{ t('audio.midi.export_to_results_hint') }}</p>
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
    background: color-mix(in srgb, var(--color-accent) 15%, transparent);
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

.settings-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 12px 0;
  border-bottom: 1px solid var(--panel-border);
  margin-bottom: 8px;
}

.settings-tab {
  padding: 6px 12px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s ease, border-color 0.15s ease;
  font-size: 13px;

  &:hover {
    color: var(--text-primary);
  }

  &.is-active {
    color: var(--color-accent);
    border-bottom-color: var(--color-accent);
  }
}


</style>
