<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'

const { t } = useI18n()

const showAdvanced = ref(false)
const wordTimestamps = ref(false)
const align = ref(false)
const conditionOnPreviousText = ref(true)
const minSilenceDurationMs = ref(200)
const vadThreshold = ref(0.3)

defineExpose({ wordTimestamps, align, conditionOnPreviousText, minSilenceDurationMs, vadThreshold })
</script>

<template>
  <div class="form-group">
    <AppToggle v-model="showAdvanced">
      {{ $t('video.whisper_advanced.title') }} <span class="label-hint">{{ $t('video.whisper_advanced.title_hint') }}</span>
    </AppToggle>

    <div v-if="showAdvanced" class="sub-params">
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
</style>
