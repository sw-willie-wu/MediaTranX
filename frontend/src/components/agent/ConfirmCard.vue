<script setup lang="ts">
import { useAgentStore } from '@/stores/agent'

const props = defineProps<{
  toolCall: { id: string; function: { name: string; arguments: string } }
}>()

const store = useAgentStore()

function approve() {
  // Phase 1: only 1 pending confirm at a time — resolve all is safe.
  store.resolveAllPendingConfirms(true)
}

function cancel() {
  store.resolveAllPendingConfirms(false)
}

function prettyArgs(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}
</script>

<template>
  <div class="confirm-card">
    <div class="confirm-card-header">
      <i class="bi bi-shield-exclamation"></i>
      <span>{{ $t('agent.confirm.title') }}</span>
    </div>
    <div class="confirm-card-body">
      <span class="tool-name">{{ props.toolCall.function.name }}</span>
      <pre class="tool-args">{{ prettyArgs(props.toolCall.function.arguments) }}</pre>
    </div>
    <div class="confirm-card-actions">
      <button class="btn-cancel" @click="cancel">{{ $t('agent.confirm.cancel') }}</button>
      <button class="btn-submit" @click="approve">{{ $t('agent.confirm.submit') }}</button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.confirm-card {
  border: 1px solid rgba(245, 158, 11, 0.4);
  border-radius: 10px;
  background: rgba(245, 158, 11, 0.06);
  overflow: hidden;
  font-size: 0.8rem;
  align-self: flex-start;
  width: 100%;
}

.confirm-card-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.6rem;
  background: rgba(245, 158, 11, 0.1);
  color: var(--color-warning);
  font-weight: 600;
  font-size: 0.78rem;
}

.confirm-card-body {
  padding: 0.4rem 0.6rem;
}

.tool-name {
  display: block;
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.2rem;
}

.tool-args {
  margin: 0;
  font-size: 0.7rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 80px;
  overflow-y: auto;
  font-family: monospace;
}

.confirm-card-actions {
  display: flex;
  gap: 0.5rem;
  padding: 0.4rem 0.6rem;
  border-top: 1px solid rgba(245, 158, 11, 0.2);
  justify-content: flex-end;
}

.btn-cancel {
  padding: 0.3rem 0.8rem;
  border: 1px solid var(--input-border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;

  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
}

.btn-submit {
  padding: 0.3rem 0.8rem;
  border: 1px solid rgba(124, 111, 173, 0.4);
  border-radius: 6px;
  background: var(--color-primary);
  color: white;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;

  &:hover { background: var(--color-primary-hover); }
}
</style>
