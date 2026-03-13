<script setup lang="ts">
const props = defineProps<{
  modelValue: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

function toggle() {
  if (!props.disabled) {
    emit('update:modelValue', !props.modelValue)
  }
}
</script>

<template>
  <label class="app-toggle" :class="{ 'is-disabled': disabled }" @click.prevent="toggle">
    <span class="app-toggle-track" :class="{ 'is-on': modelValue }">
      <span class="app-toggle-thumb"></span>
    </span>
    <span v-if="$slots.default" class="app-toggle-label">
      <slot />
    </span>
  </label>
</template>

<style scoped lang="scss">
.app-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;

  &.is-disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
}

.app-toggle-track {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: var(--input-border);
  border: 1px solid var(--panel-border);
  transition: background 0.2s ease, border-color 0.2s ease;
  flex-shrink: 0;

  &.is-on {
    background: var(--color-primary);
    border-color: var(--color-primary);
  }
}

.app-toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  transition: transform 0.2s ease;

  .is-on & {
    transform: translateX(16px);
  }
}

.app-toggle-label {
  font-size: 0.875rem;
  color: var(--text-secondary);
  line-height: 1.4;
}
</style>
