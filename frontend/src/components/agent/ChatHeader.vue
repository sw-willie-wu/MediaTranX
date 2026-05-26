<script setup lang="ts">
import { useAgentSettingsStore } from '@/stores/agentSettings'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  tokenUsage: { prompt: number; completion: number }
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'clear'): void
}>()

const settingsStore = useAgentSettingsStore()
</script>

<template>
  <div class="chat-header">
    <div class="chat-header-left">
      <span class="chat-title">{{ $t('agent.bubble.title') }}</span>
      <span v-if="settingsStore.modelChoice" class="model-badge">
        {{ settingsStore.modelChoice.split(':').pop() }}
      </span>
    </div>
    <div class="chat-header-right">
      <span v-if="props.tokenUsage.prompt > 0 || props.tokenUsage.completion > 0" class="token-counter">
        {{ $t('agent.bubble.token_count', { prompt: props.tokenUsage.prompt, completion: props.tokenUsage.completion }) }}
      </span>
      <button class="header-btn" :title="$t('common.close')" @click="emit('clear')">
        <i class="bi bi-trash3"></i>
      </button>
      <button class="header-btn" :title="$t('common.close')" @click="emit('close')">
        <i class="bi bi-x-lg"></i>
      </button>
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
