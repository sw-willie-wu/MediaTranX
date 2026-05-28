<script setup lang="ts">
/**
 * Titlebar toggle for the floating chat bubble.
 *
 * Default state: bubble hidden (this button is the only entry point).
 * Click → bubble appears + icon flips to `chat_bubble_off`.
 * Click again → bubble disappears + icon back to `chat_bubble`.
 * Visibility persists in localStorage (see useBubbleVisibility).
 *
 * Icon: Google Material Symbols Outlined (loaded via index.html link).
 * Wrapped in TitlebarButton's <button>-less variant — we render the
 * <button> here so the Material Symbols span sits inline naturally
 * instead of going through TitlebarButton's prop-driven <i class="bi">.
 */
import { useI18n } from 'vue-i18n'
import { bubbleVisible, toggleBubbleVisible } from '@/composables/useBubbleVisibility'

const { t } = useI18n()
</script>

<template>
  <button
    class="titlebar-btn chat-bubble-toggle"
    :data-tooltip="bubbleVisible ? t('agent.bubble.hide') : t('agent.bubble.show')"
    @click="toggleBubbleVisible"
  >
    <span class="material-symbols-outlined">
      {{ bubbleVisible ? 'chat_bubble_off' : 'chat_bubble' }}
    </span>
  </button>
</template>

<style lang="scss" scoped>
/* Mirror TitlebarButton.vue geometry so this sits flush with the
   neighbouring results / window-control buttons. */
.titlebar-btn {
  position: relative;
  width: 32px;
  height: 28px;
  /* Nudge left so the agent↔results gap matches the 4px results↔window-controls
     gap (TitlebarResultsButton's .results-button-wrap margin-right) — keeps the
     right-cluster icon spacing balanced instead of flush against results. */
  margin-right: 4px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  -webkit-app-region: no-drag;
  transition: background 0.15s, color 0.15s;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  /* Bottom-anchored tooltip (matches TitlebarButton pattern). */
  &[data-tooltip]:hover::after {
    content: attr(data-tooltip);
    position: absolute;
    top: calc(100% + 4px);
    left: 50%;
    transform: translateX(-50%);
    padding: 0.2rem 0.45rem;
    background: var(--tooltip-bg, rgba(0, 0, 0, 0.85));
    color: var(--tooltip-text, #fff);
    font-size: 0.7rem;
    border-radius: 4px;
    white-space: nowrap;
    pointer-events: none;
    z-index: 1100;
  }
}

.material-symbols-outlined {
  /* Match TitlebarButton's 0.85rem (~13.6px) so this sits visually
     flush with the neighbouring Bootstrap Icons. opsz also tuned down
     for crisp rendering at the smaller size. Nudge down 2px so the
     glyph's optical centre aligns with the neighbouring icons (the
     Material Symbols baseline sits higher than Bootstrap Icons'). */
  font-size: 0.95rem;
  font-variation-settings:
    'FILL' 0,
    'wght' 400,
    'GRAD' 0,
    'opsz' 20;
  line-height: 1;
  transform: translateY(1px);
}
</style>
