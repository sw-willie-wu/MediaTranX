<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const { toasts, dismiss } = useToast()

function iconFor(type: string, icon?: string) {
  if (icon) return icon
  switch (type) {
    case 'success': return 'bi-check-circle-fill'
    case 'error': return 'bi-exclamation-circle-fill'
    default: return 'bi-info-circle-fill'
  }
}
</script>

<template>
  <Teleport to="body">
    <TransitionGroup name="toast" tag="div" class="toast-container">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="toast-item"
        :class="`toast-${toast.type}`"
      >
        <i class="bi toast-icon" :class="iconFor(toast.type, toast.icon)"></i>
        <span class="toast-message">{{ toast.message }}</span>
        <button
          v-if="toast.action"
          class="toast-action"
          @click="() => { toast.action!.callback(); dismiss(toast.id) }"
        >{{ toast.action.label }}</button>
        <button class="toast-close" @click="dismiss(toast.id)">
          <i class="bi bi-x"></i>
        </button>
      </div>
    </TransitionGroup>
  </Teleport>
</template>

<style lang="scss" scoped>
.toast-container {
  position: fixed;
  top: 48px;
  right: 16px;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast-item {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  min-width: 260px;
  max-width: 380px;
  background: rgba(30, 30, 40, 0.75);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: var(--text-primary);
  font-size: 0.85rem;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.toast-icon {
  font-size: 1rem;
  flex-shrink: 0;
}

.toast-info .toast-icon { color: #60a5fa; }
.toast-success .toast-icon { color: #34d399; }
.toast-error .toast-icon { color: #f87171; }

.toast-message {
  flex: 1;
  line-height: 1.4;
}

.toast-action {
  flex-shrink: 0;
  padding: 3px 10px;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 5px;
  color: var(--text-primary);
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease;
  white-space: nowrap;

  &:hover {
    background: rgba(255, 255, 255, 0.25);
  }
}

.toast-close {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: color 0.15s ease;
  flex-shrink: 0;

  i { font-size: 1rem; }

  &:hover {
    color: var(--text-primary);
  }
}

// Transition
.toast-enter-active {
  transition: all 0.3s ease;
}

.toast-leave-active {
  transition: all 0.25s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(60px);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(60px);
}

.toast-move {
  transition: transform 0.25s ease;
}
</style>
