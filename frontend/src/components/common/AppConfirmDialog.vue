<script setup lang="ts">
import { useConfirm } from '@/composables/useConfirm'
import { useI18n } from 'vue-i18n'

const { visible, options, handleConfirm, handleCancel } = useConfirm()
const { t } = useI18n()

function onOverlayClick(e: MouseEvent) {
  if ((e.target as HTMLElement).classList.contains('confirm-overlay')) {
    handleCancel()
  }
}

function onKeydown(e: KeyboardEvent) {
  if (!visible.value) return
  if (e.key === 'Escape') handleCancel()
  if (e.key === 'Enter') handleConfirm()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="confirm-fade">
      <div
        v-if="visible"
        class="confirm-overlay"
        @click="onOverlayClick"
        @keydown="onKeydown"
        tabindex="-1"
        ref="overlayRef"
      >
        <div class="confirm-dialog">
          <div class="confirm-icon">
            <i
              class="bi"
              :class="options.type === 'danger' ? 'bi-exclamation-triangle-fill' : options.type === 'warning' ? 'bi-question-circle-fill' : 'bi-info-circle-fill'"
            />
          </div>
          <h3 v-if="options.title" class="confirm-title">{{ options.title }}</h3>
          <p class="confirm-message">{{ options.message }}</p>
          <div class="confirm-actions">
            <button class="confirm-btn cancel" @click="handleCancel">
              {{ options.cancelLabel || t('common.cancel') }}
            </button>
            <button
              class="confirm-btn primary"
              :class="{ danger: options.type === 'danger' }"
              @click="handleConfirm"
            >
              {{ options.confirmLabel || t('common.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style lang="scss" scoped>
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 20000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(15px);
  -webkit-backdrop-filter: blur(15px);
}

.confirm-dialog {
  background: rgba(30, 30, 50, 0.35);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 1.5rem 2rem;
  min-width: 320px;
  max-width: 420px;
  text-align: center;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
}

.confirm-icon {
  margin-bottom: 0.75rem;

  i {
    font-size: 2rem;
    color: var(--color-warning);
  }
}

.confirm-title {
  color: var(--text-primary);
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.confirm-message {
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 1.25rem;
}

.confirm-actions {
  display: flex;
  gap: 0.75rem;
  justify-content: center;
}

.confirm-btn {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;

  &.cancel {
    background: var(--input-bg);
    color: var(--text-secondary);
    border: 1px solid var(--panel-border);

    &:hover {
      background: var(--panel-bg-hover);
      color: var(--text-primary);
    }
  }

  &.primary {
    background: var(--color-primary);
    color: white;

    &:hover {
      background: var(--color-primary-hover);
    }

    &.danger {
      background: var(--color-danger);

      &:hover {
        background: #dc2626;
      }
    }
  }
}

.confirm-fade-enter-active,
.confirm-fade-leave-active {
  transition: opacity 0.15s ease;
}

.confirm-fade-enter-from,
.confirm-fade-leave-to {
  opacity: 0;
}
</style>
