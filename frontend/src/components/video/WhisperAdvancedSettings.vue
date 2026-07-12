<script setup lang="ts">
/**
 * WhisperAdvancedSettings — whisper 進階設定子元件（統一參數元件 spec §5；批 2 Task 2.4
 * v-model 化；收尾批 W1-3 移除雙軌相容——舊 uncontrolled 呼叫端 SubtitlePanel.vue／
 * AudioTranscribePanel.vue 皆已在遷移時整檔刪除或改走本元件的受控模式，現在三個消費者
 * （TranscribeParams/SummaryParams/SubtitleParams，皆 components/params/ 下的
 * 統一參數元件）一律 `:model-value` 受控，元件內部不再區分受控/非受控——`modelValue` 現在
 * 恆有值，舊 defineExpose（供 template ref 直接改寫內部 ref 用）已無消費者一併移除。
 *
 * 內部 5 個 ref 的初值來自 modelValue，之後外部寫入（watch props.modelValue）與內部使用者
 * 操作（watch 5 個 ref → emit update:modelValue）雙向同步；one-shot lastEmitted echo 判別沿
 * CutParams.vue pattern，避免 emit 觸發的 props 更新又被 watch 誤判成「外部寫入」而重新套用
 * 一次造成迴圈或以本地值覆蓋別的並發外部寫入。
 */
import { ref, watch } from 'vue'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'

export interface WhisperAdvancedValue {
  word_timestamps: boolean
  align: boolean
  condition_on_previous_text: boolean
  min_silence_duration_ms: number
  vad_threshold: number
}

const props = withDefaults(
  defineProps<{ embedded?: boolean; modelValue?: WhisperAdvancedValue }>(),
  { embedded: false },
)
const emit = defineEmits<{ 'update:modelValue': [WhisperAdvancedValue] }>()

const showAdvanced = ref(false)
const wordTimestamps = ref(props.modelValue?.word_timestamps ?? false)
const align = ref(props.modelValue?.align ?? false)
const conditionOnPreviousText = ref(props.modelValue?.condition_on_previous_text ?? true)
const minSilenceDurationMs = ref(props.modelValue?.min_silence_duration_ms ?? 200)
const vadThreshold = ref(props.modelValue?.vad_threshold ?? 0.3)

function currentValue(): WhisperAdvancedValue {
  return {
    word_timestamps: wordTimestamps.value,
    align: align.value,
    condition_on_previous_text: conditionOnPreviousText.value,
    min_silence_duration_ms: minSilenceDurationMs.value,
    vad_threshold: vadThreshold.value,
  }
}

function shallowEqualValue(a: WhisperAdvancedValue, b: WhisperAdvancedValue): boolean {
  return (
    a.word_timestamps === b.word_timestamps &&
    a.align === b.align &&
    a.condition_on_previous_text === b.condition_on_previous_text &&
    a.min_silence_duration_ms === b.min_silence_duration_ms &&
    a.vad_threshold === b.vad_threshold
  )
}

let lastEmitted: WhisperAdvancedValue | null = null

// 內部 5 個 ref 任一變動 → emit 完整 patch（三個消費者皆受控，恆有 modelValue）。
watch([wordTimestamps, align, conditionOnPreviousText, minSilenceDurationMs, vadThreshold], () => {
  const next = currentValue()
  lastEmitted = next
  emit('update:modelValue', next)
})

// 外部寫入 props.modelValue（host setField/setParams/seed）→ 同步回 5 個內部 ref；
// one-shot echo 判別：本次 watch 觸發若等於上次自己 emit 的值，視為回流，不重推（避免迴圈）。
watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqualValue(echo, v)) return
    wordTimestamps.value = v.word_timestamps
    align.value = v.align
    conditionOnPreviousText.value = v.condition_on_previous_text
    minSilenceDurationMs.value = v.min_silence_duration_ms
    vadThreshold.value = v.vad_threshold
  },
  { deep: true },
)
</script>

<template>
  <div class="form-group">
    <AppToggle v-if="!props.embedded" v-model="showAdvanced">
      {{ $t('video.whisper_advanced.title') }} <span class="label-hint">{{ $t('video.whisper_advanced.title_hint') }}</span>
    </AppToggle>
    <label v-else class="sub-section-label">
      {{ $t('video.whisper_advanced.section_title') }} <span class="label-hint">{{ $t('video.whisper_advanced.title_hint') }}</span>
    </label>

    <div v-if="props.embedded || showAdvanced" class="sub-params">
      <div class="option-row">
        <AppToggle
          :modelValue="!conditionOnPreviousText"
          @update:modelValue="v => conditionOnPreviousText = !v"
        >{{ $t('video.whisper_advanced.independent_segments') }}</AppToggle>
        <span class="form-hint">{{ $t('video.whisper_advanced.independent_hint') }}</span>
      </div>

      <div class="option-row">
        <AppToggle v-model="wordTimestamps">{{ $t('video.whisper_advanced.word_timestamps') }}</AppToggle>
        <span class="form-hint">{{ $t('video.whisper_advanced.word_timestamps_hint') }}</span>
      </div>

      <div class="option-row">
        <AppToggle v-model="align">{{ $t('video.whisper_advanced.align') }}</AppToggle>
        <span class="form-hint">{{ $t('video.whisper_advanced.align_hint') }}</span>
      </div>

      <div class="form-group">
        <label class="sub-label">
          {{ $t('video.whisper_advanced.min_silence') }}
          <span class="param-value">{{ minSilenceDurationMs }} {{ $t('video.whisper_advanced.milliseconds') }}</span>
        </label>
        <AppRange v-model="minSilenceDurationMs" :min="100" :max="2000" :step="100" />
        <small class="form-hint">{{ $t('video.whisper_advanced.min_silence_hint') }}</small>
      </div>

      <div class="form-group">
        <label class="sub-label">
          {{ $t('video.whisper_advanced.vad_threshold') }}
          <span class="param-value">{{ vadThreshold.toFixed(1) }}</span>
        </label>
        <AppRange v-model="vadThreshold" :min="0.1" :max="0.9" :step="0.1" />
        <small class="form-hint">{{ $t('video.whisper_advanced.vad_threshold_hint') }}</small>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.label-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-weight: normal;
}

.option-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sub-section-label {
  display: block;
  margin: 0.5rem 0 0.25rem;
  font-size: 0.85rem;
  color: var(--text-muted);
  font-weight: 600;
}
</style>
