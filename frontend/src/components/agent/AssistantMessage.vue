<script setup lang="ts">
import ToolCallCard from './ToolCallCard.vue'

const props = defineProps<{
  content: string
  toolCalls: Array<{ id: string; function: { name: string; arguments: string } }>
  isRunning: boolean
}>()

/**
 * Minimal markdown rendering:
 * - **bold** → <strong>
 * - line breaks → <br>
 * Phase 2 can add a real markdown lib.
 */
function renderText(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}
</script>

<template>
  <div class="assistant-message">
    <div class="assistant-bubble">
      <!-- Text content -->
      <span
        v-if="content"
        class="assistant-text"
        v-html="renderText(content)"
      ></span>
      <!-- Streaming cursor -->
      <span v-if="isRunning && content" class="stream-cursor">▎</span>
      <!-- Thinking placeholder when no content yet -->
      <span v-if="isRunning && !content && toolCalls.length === 0" class="thinking-label">
        {{ $t('agent.bubble.thinking') }}
      </span>
    </div>

    <!-- Tool calls embedded in assistant message -->
    <ToolCallCard
      v-for="tc in toolCalls"
      :key="tc.id"
      :tool-call="tc"
      :status="'done'"
    />
  </div>
</template>

<style lang="scss" scoped>
.assistant-message {
  align-self: flex-start;
  max-width: 90%;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.assistant-bubble {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  padding: 0.5rem 0.75rem;
  border-radius: 12px 12px 12px 2px;
  font-size: 0.85rem;
  line-height: 1.6;
  color: var(--text-primary);
  word-break: break-word;
  min-height: 1.4rem;
}

.assistant-text {
  white-space: pre-wrap;
}

.stream-cursor {
  display: inline-block;
  color: var(--color-primary);
  font-weight: bold;
  animation: cursor-blink 0.8s step-end infinite;
  margin-left: 1px;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}

.thinking-label {
  color: var(--text-muted);
  font-style: italic;
  font-size: 0.8rem;
}
</style>
