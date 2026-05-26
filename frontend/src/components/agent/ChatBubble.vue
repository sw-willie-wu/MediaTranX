<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { useAgent } from '@/composables/useAgent'
import ChatHeader from './ChatHeader.vue'
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'

const store = useAgentStore()
const agent = useAgent()
const expanded = ref(false)

function toggle() {
  expanded.value = !expanded.value
}

function close() {
  expanded.value = false
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && expanded.value) {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <!-- Collapsed: round bubble button -->
    <button
      v-if="!expanded"
      class="chat-bubble-btn"
      :class="{ 'is-running': store.isRunning }"
      @click="toggle"
      :aria-label="$t('agent.bubble.title')"
    >
      <i class="bi bi-robot"></i>
      <span v-if="store.isRunning" class="bubble-pulse"></span>
    </button>

    <!-- Expanded: chat panel -->
    <div v-else class="chat-bubble-panel">
      <ChatHeader
        :token-usage="store.threadTokens"
        @close="close"
        @clear="agent.clearHistory()"
      />
      <ChatMessages
        :messages="agent.messages.value"
        :transient="store.transient"
        :is-running="store.isRunning"
      />
      <ChatInput
        :disabled="store.isRunning"
        @send="agent.sendUserText"
        @cancel="agent.cancelRun()"
        :is-running="store.isRunning"
      />
    </div>
  </Teleport>
</template>

<style lang="scss" scoped>
.chat-bubble-btn {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--color-primary);
  border: none;
  color: white;
  font-size: 1.2rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  z-index: 9000;
  transition: transform 0.2s ease-in-out, background 0.2s ease-in-out;
  position: fixed;

  &:hover {
    background: var(--color-primary-hover);
    transform: scale(1.08);
  }

  &.is-running {
    background: var(--color-primary);
  }
}

.bubble-pulse {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-success);
  animation: pulse-ring 1.4s ease-out infinite;
}

@keyframes pulse-ring {
  0%   { transform: scale(0.9); opacity: 1; }
  70%  { transform: scale(1.3); opacity: 0.5; }
  100% { transform: scale(0.9); opacity: 1; }
}

.chat-bubble-panel {
  position: fixed;
  bottom: 84px;
  right: 24px;
  width: 380px;
  height: 600px;
  border-radius: 12px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  z-index: 9000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: panel-in 0.2s ease-in-out;
}

@keyframes panel-in {
  from { opacity: 0; transform: scale(0.96) translateY(8px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}
</style>
