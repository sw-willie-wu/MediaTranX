<script setup lang="ts">
import { getToolLabel, type ToolType } from '@/utils/mediaType'

const props = defineProps<{
  visible: boolean
  target: ToolType | null
}>()

const emit = defineEmits<{
  dismiss: []
  goToTool: []
}>()
</script>

<template>
  <Transition name="overlay-fade">
    <div v-if="visible" class="unsupported-overlay" @click.self="emit('dismiss')">
      <div class="unsupported-card">
        <i class="bi bi-exclamation-triangle"></i>
        <p>此工具不支援此檔案格式</p>
        <button v-if="target" class="goto-btn" @click="emit('goToTool')">
          前往{{ getToolLabel(target) }}
        </button>
        <button class="dismiss-btn" @click="emit('dismiss')">關閉</button>
      </div>
    </div>
  </Transition>
</template>

<style lang="scss" scoped>
.unsupported-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.unsupported-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 2rem 2.5rem;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 16px;
  text-align: center;

  > i {
    font-size: 2.5rem;
    color: var(--color-warning);
  }

  > p {
    color: var(--text-primary);
    font-size: 1rem;
    margin: 0;
  }
}

.goto-btn {
  padding: 0.5rem 1.25rem;
  background: var(--color-primary);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.85rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--color-primary-hover);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
  }
}

.dismiss-btn {
  padding: 0.35rem 1rem;
  background: transparent;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    color: var(--text-primary);
    border-color: var(--text-muted);
  }
}

.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 0.2s ease;
}

.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}
</style>
