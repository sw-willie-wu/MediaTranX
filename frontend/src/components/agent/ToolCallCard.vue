<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  toolCall: { id: string; function: { name: string; arguments: string } }
  status: 'running' | 'done' | 'error'
}>()

const expanded = ref(false)
const { t, te } = useI18n()

function toolLabel(name: string): string {
  const key = `agent.tool.${name}`
  return te(key) ? t(key) : name
}

function prettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}
</script>

<template>
  <div class="tool-call-card" :class="`status-${status}`">
    <button class="tool-call-header" @click="expanded = !expanded">
      <span class="tool-status-icon">
        <i v-if="status === 'running'" class="bi bi-arrow-repeat spin"></i>
        <i v-else-if="status === 'error'" class="bi bi-x-circle-fill text-danger"></i>
        <i v-else class="bi bi-check-circle-fill text-success"></i>
      </span>
      <span class="tool-name">{{ toolLabel(props.toolCall.function.name) }}</span>
      <i class="bi expand-icon" :class="expanded ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
    </button>

    <div v-if="expanded" class="tool-call-args">
      <pre>{{ prettyJson(props.toolCall.function.arguments) }}</pre>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.tool-call-card {
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  overflow: hidden;
  font-size: 0.78rem;

  &.status-running {
    border-color: rgba(245, 158, 11, 0.3);
  }
  &.status-error {
    border-color: rgba(239, 68, 68, 0.3);
  }
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
  padding: 0.3rem 0.5rem;
  background: var(--input-bg);
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-family: inherit;
  text-align: left;

  &:hover {
    background: var(--panel-bg-hover);
  }
}

.tool-status-icon {
  flex-shrink: 0;
  font-size: 0.75rem;
}

.spin {
  animation: tool-spin 1s linear infinite;
}

@keyframes tool-spin {
  to { transform: rotate(360deg); }
}

.text-danger { color: var(--color-danger); }
.text-success { color: var(--color-success); }

.tool-name {
  flex: 1;
  font-weight: 500;
  color: var(--text-primary);
}

.expand-icon {
  flex-shrink: 0;
  font-size: 0.65rem;
  color: var(--text-muted);
}

.tool-call-args {
  padding: 0.4rem 0.5rem;
  background: var(--input-bg);
  border-top: 1px solid var(--panel-border);

  pre {
    margin: 0;
    font-size: 0.72rem;
    line-height: 1.5;
    color: var(--text-secondary);
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 120px;
    overflow-y: auto;
    font-family: monospace;
  }
}
</style>
