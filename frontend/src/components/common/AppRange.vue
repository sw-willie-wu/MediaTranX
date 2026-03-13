<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue: number
  min?: number
  max?: number
  step?: number
  disabled?: boolean
}>(), {
  min: 0,
  max: 100,
  step: 1,
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void
}>()

function onInput(e: Event) {
  const target = e.target as HTMLInputElement
  emit('update:modelValue', Number(target.value))
}
</script>

<template>
  <input
    type="range"
    class="app-range"
    :value="modelValue"
    :min="min"
    :max="max"
    :step="step"
    :disabled="disabled"
    @input="onInput"
  />
</template>

<style scoped>
.app-range {
  width: 100%;
  height: 20px;
  padding: 8px 0;
  appearance: none;
  background: transparent;
  cursor: pointer;
}

.app-range:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.app-range::-webkit-slider-runnable-track {
  height: 4px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
}

.app-range::-webkit-slider-thumb {
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-primary);
  margin-top: -4px;
  transition: transform 0.1s ease;
}

.app-range::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}

</style>

<!-- Light theme overrides (non-scoped for pseudo-element compatibility) -->
<style>
[data-theme="light"] .app-range::-webkit-slider-runnable-track {
  background: rgba(255, 255, 255, 1);
}

[data-theme="light"] .app-range::-webkit-slider-thumb {
  background: var(--color-primary);
}
</style>
