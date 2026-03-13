<script setup lang="ts">
import { ref } from 'vue'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'

const showAdvanced = ref(false)
const wordTimestamps = ref(false)
const conditionOnPreviousText = ref(true)
const minSilenceDurationMs = ref(200)
const vadThreshold = ref(0.3)

defineExpose({ wordTimestamps, conditionOnPreviousText, minSilenceDurationMs, vadThreshold })
</script>

<template>
  <div class="form-group">
    <AppToggle v-model="showAdvanced">
      進階分句設定 <span class="label-hint">（適合多人對話）</span>
    </AppToggle>

    <div v-if="showAdvanced" class="sub-params">
      <div class="option-row">
        <AppToggle
          :modelValue="!conditionOnPreviousText"
          @update:modelValue="v => conditionOnPreviousText = !v"
        >獨立辨識每段語音</AppToggle>
        <span class="form-hint">關閉上下文關聯，避免句子合併</span>
      </div>

      <div class="option-row">
        <AppToggle v-model="wordTimestamps">詞級時間戳</AppToggle>
        <span class="form-hint">更精確的分句邊界</span>
      </div>

      <div class="form-group">
        <label class="sub-label">
          最小靜音時長
          <span class="param-value">{{ minSilenceDurationMs }} ms</span>
        </label>
        <AppRange v-model="minSilenceDurationMs" :min="100" :max="2000" :step="100" />
        <small class="form-hint">停頓超過此時長會分句（預設 200ms）</small>
      </div>

      <div class="form-group">
        <label class="sub-label">
          VAD 敏感度
          <span class="param-value">{{ vadThreshold.toFixed(1) }}</span>
        </label>
        <AppRange v-model="vadThreshold" :min="0.1" :max="0.9" :step="0.1" />
        <small class="form-hint">越低越敏感，更容易分句（預設 0.3）</small>
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
