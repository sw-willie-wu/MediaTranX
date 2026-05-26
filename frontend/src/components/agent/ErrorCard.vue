<script setup lang="ts">
const props = defineProps<{
  errorKey: string
  onRetry?: () => void
}>()
</script>

<template>
  <div class="error-card">
    <i class="bi bi-exclamation-triangle-fill error-icon"></i>
    <span class="error-message">{{ $t(props.errorKey) }}</span>
    <button v-if="props.onRetry" class="retry-btn" @click="props.onRetry?.()">
      {{ $t('common.retry') }}
    </button>
  </div>
</template>

<style lang="scss" scoped>
.error-card {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  padding: 0.5rem 0.6rem;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
  font-size: 0.8rem;
  align-self: flex-start;
  width: 100%;
}

.error-icon {
  color: var(--color-danger);
  flex-shrink: 0;
  margin-top: 1px;
}

.error-message {
  flex: 1;
  color: var(--text-secondary);
  line-height: 1.4;
}

.retry-btn {
  flex-shrink: 0;
  padding: 0.2rem 0.6rem;
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 5px;
  background: transparent;
  color: var(--color-danger);
  font-size: 0.75rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;

  &:hover { background: rgba(239, 68, 68, 0.1); }
}
</style>
