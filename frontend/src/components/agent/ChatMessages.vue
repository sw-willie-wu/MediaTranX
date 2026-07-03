<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import type { Message } from '@/composables/useAgent'
import type { TransientBuffer } from '@/stores/agent'
import { toolResultPreview } from '@/composables/agentMessagePreview'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import ToolCallCard from './ToolCallCard.vue'
import ConfirmCard from './ConfirmCard.vue'

const props = defineProps<{
  messages: Message[]
  transient: TransientBuffer | null
  isRunning: boolean
  runError: string | null
}>()

const listRef = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
    }
  })
}

watch(() => props.messages.length, scrollToBottom)
watch(() => props.transient?.text, scrollToBottom)

// The panel is v-if-mounted (ChatBubble closes by unmounting), so reopening
// remounts this component at scrollTop=0. The watchers above only fire on
// CHANGE, not on mount — so without this, reopening a non-empty chat lands at
// the top instead of the latest message. Scroll to bottom on mount.
onMounted(scrollToBottom)

function toolCallIdToName(toolCallId: string, messages: Message[]): string {
  for (const m of messages) {
    if (m.role === 'assistant') {
      const tc = m.toolCalls?.find((t) => t.id === toolCallId)
      if (tc) return tc.function?.name ?? toolCallId
    }
  }
  return toolCallId
}
</script>

<template>
  <div ref="listRef" class="chat-messages">
    <div v-if="messages.length === 0 && !isRunning" class="messages-empty">
      {{ $t('agent.bubble.empty') }}
    </div>

    <template v-for="(msg, idx) in messages" :key="idx">
      <!-- User -->
      <UserMessage v-if="msg.role === 'user'" :content="(msg as any).content" />

      <!-- Assistant: text + tool calls -->
      <AssistantMessage
        v-else-if="msg.role === 'assistant'"
        :content="(msg as any).content"
        :tool-calls="(msg as any).toolCalls ?? []"
        :is-running="false"
      />

      <!-- Tool result (inline preview) -->
      <!-- v-for over a single-item array lets us call toolResultPreview() once per row -->
      <template v-else-if="msg.role === 'tool'">
        <div
          v-for="(preview, previewIdx) in [toolResultPreview((msg as any).content)]"
          :key="previewIdx"
          class="tool-result-row"
        >
          <span class="tool-result-name">{{ toolCallIdToName((msg as any).toolCallId, messages) }}</span>
          <span
            v-if="preview.icon"
            class="tool-result-icon"
            :class="`tool-result-icon--${preview.status}`"
          >{{ preview.icon }}</span>
          <span class="tool-result-text">{{ preview.text }}</span>
        </div>
      </template>

      <!-- Confirm card (pending only) -->
      <ConfirmCard
        v-else-if="msg.role === 'tool_confirm' && (msg as any).status === 'pending'"
        :tool-call="(msg as any).toolCall"
      />
    </template>

    <!-- Transient streaming preview -->
    <template v-if="isRunning && transient">
      <AssistantMessage
        v-if="transient.text"
        :content="transient.text"
        :tool-calls="[]"
        :is-running="true"
      />
      <template v-if="transient.toolCallsBuf.size > 0">
        <ToolCallCard
          v-for="[id, tc] in transient.toolCallsBuf"
          :key="id"
          :tool-call="{ id, function: { name: tc.name, arguments: tc.args } }"
          :status="'running'"
        />
      </template>
    </template>

    <!-- "Thinking…" indicator when running but nothing in transient yet -->
    <div
      v-if="isRunning && (!transient || (!transient.text && transient.toolCallsBuf.size === 0))"
      class="thinking-row"
    >
      <span class="thinking-dot"></span>
      <span class="thinking-dot"></span>
      <span class="thinking-dot"></span>
    </div>

    <!-- Transient run-error label (below the last message; not a bubble, not persisted) -->
    <div v-if="runError && !isRunning" class="run-error-row">
      <span class="run-error-icon">⚠️</span>
      <span class="run-error-text">{{ runError }}</span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); border-radius: 2px; }
  &::-webkit-scrollbar-thumb:hover { background: var(--scrollbar-thumb-hover); }
}

// Messages must never be flex-shrunk. In this column flex + overflow-y:auto
// scroll container, a child with `overflow:hidden` (e.g. ConfirmCard) has its
// `min-height:auto` resolved to 0 by the flexbox spec, so flexbox collapses it
// to ~1px once the list overflows — clipping its buttons and leaving only the
// amber border ("orange line, no options" confirm-card bug). flex-shrink:0 keeps
// every message at its natural height; the container scrolls instead.
.chat-messages > * {
  flex-shrink: 0;
}

.messages-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 0.8rem;
  text-align: center;
}

.tool-result-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  background: var(--input-bg);
  font-size: 0.75rem;
  align-self: flex-start;
  max-width: 90%;
}

.tool-result-name {
  color: var(--text-muted);
  font-weight: 500;
  white-space: nowrap;
}

.tool-result-text {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

// UX-1: differentiate success (✓) vs error (✗) tool-result icons so users
// can tell at a glance which tool calls succeeded vs failed. Matches the
// same pattern as ToolCallCard.vue's .text-danger / .text-success classes.
.tool-result-icon {
  font-weight: 600;
  flex-shrink: 0;

  &--success { color: var(--color-success); }
  &--error   { color: var(--color-danger); }
}

.thinking-row {
  display: flex;
  gap: 4px;
  padding: 0.5rem 0.25rem;
  align-items: center;
}

.thinking-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: thinking-bounce 1.2s ease-in-out infinite;

  &:nth-child(2) { animation-delay: 0.15s; }
  &:nth-child(3) { animation-delay: 0.3s; }
}

@keyframes thinking-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30%            { transform: translateY(-5px); opacity: 1; }
}

.run-error-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.5rem;
  font-size: 0.75rem;
  color: var(--color-danger);
  align-self: flex-start;
}
.run-error-icon { flex-shrink: 0; }
</style>
