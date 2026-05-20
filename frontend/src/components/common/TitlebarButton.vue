<script setup lang="ts">
/**
 * Shared titlebar icon button.
 *
 * Used by Titlebar.vue (undo/redo/save-as/extra actions) and
 * TitlebarResultsButton.vue. Encapsulates layout, hover/active/disabled
 * behavior, highlighted state, and the bottom-tooltip pattern. Per-component
 * logic (click handler, icon choice, badge) lives in the consumer.
 */
withDefaults(defineProps<{
  icon?: string
  tooltip?: string
  disabled?: boolean
  /** White text (currently-meaningful action, e.g. canSaveAs / has content). */
  highlighted?: boolean
  /** Purple-filled toggle state (e.g. compare-on, dropdown-open). */
  active?: boolean
}>(), {
  disabled: false,
  highlighted: false,
  active: false,
})
</script>

<template>
  <button
    class="titlebar-btn"
    :class="{ 'is-highlighted': highlighted && !active, 'is-active': active }"
    :disabled="disabled"
    :data-tooltip="tooltip"
  >
    <i v-if="icon" :class="['bi', icon]"></i>
    <slot />
  </button>
</template>

<style lang="scss" scoped>
.titlebar-btn {
  position: relative;
  width: 32px;
  height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 0.85rem;

  &:hover:not(:disabled) {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }
  &:active:not(:disabled) {
    background: var(--panel-bg-active);
  }
  &:disabled {
    opacity: 0.25;
    cursor: default;
  }

  &.is-highlighted {
    color: var(--text-primary);
  }

  &.is-active {
    background: var(--color-primary);
    color: #fff;
    opacity: 1;

    &:hover { background: var(--color-primary-hover); }
  }

  // Tooltip — bottom-center
  &::after {
    content: attr(data-tooltip);
    position: absolute;
    top: calc(100% + 4px);
    left: 50%;
    transform: translateX(-50%);
    padding: 4px 10px;
    background: var(--panel-bg-active);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.75rem;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s ease;
    z-index: 100;
  }
  &:hover:not(:disabled):not(.is-active)::after { opacity: 1; }
}

.flip-v { transform: scaleY(-1); }
</style>
