<script setup lang="ts">
import { useAgentStore } from '@/stores/agent'
import { useAgent } from '@/composables/useAgent'
import { useI18n } from 'vue-i18n'

const store = useAgentStore()
const agent = useAgent()
const { t } = useI18n()

function bannerLabel(): string {
  const action = store.currentAction
  if (!action.key) return t('agent.banner.prefix') + t('agent.banner.queued')
  return t('agent.banner.prefix') + t(action.key, action.args as any)
}
</script>

<template>
  <div class="agent-run-banner">
    <span class="banner-label">{{ bannerLabel() }}</span>
    <button class="banner-cancel" @click="agent.cancelRun()">
      <i class="bi bi-x-lg"></i>
    </button>
  </div>
</template>

<style lang="scss" scoped>
.agent-run-banner {
  position: fixed;
  top: 40px; /* below titlebar */
  left: 0;
  right: 0;
  height: 32px;
  background: rgba(245, 158, 11, 0.15);
  border-bottom: 1px solid rgba(245, 158, 11, 0.3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.75rem;
  z-index: 900;
  backdrop-filter: blur(4px);
}

.banner-label {
  font-size: 0.78rem;
  color: var(--color-warning);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.banner-cancel {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--color-warning);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  transition: background 0.15s;
  flex-shrink: 0;

  &:hover { background: rgba(245, 158, 11, 0.2); }
}
</style>
