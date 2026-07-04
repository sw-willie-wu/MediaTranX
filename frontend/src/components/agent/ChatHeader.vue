<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAgentSettingsStore, nextPolicy } from '@/stores/agentSettings'
import { parseModelValue } from '@/composables/useModelOptions'

const props = defineProps<{
  tokenUsage: { prompt: number; completion: number }
}>()

const emit = defineEmits<{
  (e: 'back'): void
}>()

const { t } = useI18n()
const settingsStore = useAgentSettingsStore()

/** Short badge label for the current confirmation policy (distinct from the
 * verbose settings-radio labels, which overflow this narrow header). */
const policyShort = computed(() => t(`agent.bubble.policy_short.${settingsStore.policy}`))

/** Cycle the confirmation policy to the next mode, applied immediately. */
function cyclePolicy() {
  settingsStore.setPolicy(nextPolicy(settingsStore.policy))
}

/**
 * Human-readable label for the badge.
 * Local models are stored as `family:size[:quant]` (e.g. `qwen3:8b:Q4_K_M`)
 * — drop the quant suffix and show `family:size` (`qwen3:8b`).
 * Remote models are stored as `remote:<provider>:<connId>:<modelId>` (e.g.
 * `remote:openai:1:gpt-4o-mini`) — show the modelId. Note modelId itself can
 * contain a colon (Ollama tags like `gpt-oss:120b`), so we reuse the canonical
 * parseModelValue (slice(3).join(':')) rather than a naive `.pop()`, which
 * would drop everything before the tag colon and show just `120b`.
 */
const modelLabel = computed(() => {
  const m = settingsStore.modelChoice
  if (!m) return ''
  if (m.startsWith('remote:')) return parseModelValue(m).modelId || m
  return m.split(':').slice(0, 2).join(':')
})
</script>

<template>
  <div class="chat-header">
    <div class="chat-header-left">
      <button
        class="header-btn header-back-btn"
        :title="$t('agent.session.back')"
        :aria-label="$t('agent.session.back')"
        @click="emit('back')"
      >
        <i class="bi bi-arrow-left"></i>
      </button>
      <span class="chat-title">{{ $t('agent.bubble.title') }}</span>
      <span v-if="modelLabel" class="model-badge">
        {{ modelLabel }}
      </span>
      <button
        type="button"
        class="policy-badge"
        :title="$t('agent.bubble.policy_tooltip', { mode: policyShort })"
        :aria-label="$t('agent.bubble.policy_tooltip', { mode: policyShort })"
        @click="cyclePolicy"
      >{{ policyShort }}</button>
    </div>
    <div class="chat-header-right">
      <span v-if="props.tokenUsage.prompt > 0 || props.tokenUsage.completion > 0" class="token-counter">
        {{ $t('agent.bubble.token_count', { prompt: props.tokenUsage.prompt, completion: props.tokenUsage.completion }) }}
      </span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--panel-border);
  flex-shrink: 0;
  min-height: 42px;
}

.chat-header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.chat-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.model-badge {
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: rgba(124, 111, 173, 0.2);
  color: var(--color-accent);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Confirmation-policy badge: same pill shape as the model badge, but a distinct
   tint + interactive (click to cycle the policy). max-width/ellipsis is a
   defensive guard — the short labels never trigger it. */
.policy-badge {
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border: none;
  border-radius: 4px;
  background: rgba(124, 111, 173, 0.35);
  color: var(--text-primary);
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: rgba(124, 111, 173, 0.55);
  }
}

.chat-header-right {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-shrink: 0;
}

.token-counter {
  font-size: 0.68rem;
  color: var(--text-muted);
  white-space: nowrap;
  margin-right: 0.25rem;
}

.header-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8rem;
  transition: background 0.15s, color 0.15s;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }
}
</style>
