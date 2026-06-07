<script setup lang="ts">
/**
 * Titlebar toggle for the floating chat bubble.
 *
 * Default state: bubble hidden (this button is the only entry point).
 * Click → bubble appears + icon switches to the filled chat glyph.
 * Click again → bubble disappears + icon back to the outline chat glyph.
 * Visibility persists in localStorage (see useBubbleVisibility).
 *
 * Icon: Bootstrap Icons, bundled via main.ts (same as every other titlebar
 * icon). The glyph SWITCHES between states — outline `bi-chat-dots` (hidden,
 * click to open) ↔ filled `bi-chat-dots-fill` (shown, click to hide) —
 * mirroring the original chat_bubble ↔ chat_bubble_off two-icon toggle.
 * (Previously used a Google Material Symbols CDN webfont — the only such
 * outlier in the app — which broke offline / on slow first paint because the
 * ligature couldn't resolve and rendered as raw text, displacing the cluster.
 * Bootstrap Icons has no chat-with-slash glyph, so filled = "on" stands in
 * for the slashed "off" icon.)
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TitlebarButton from './common/TitlebarButton.vue'
import { bubbleVisible, toggleBubbleVisible } from '@/composables/useBubbleVisibility'

const { t } = useI18n()
const icon = computed(() => (bubbleVisible.value ? 'bi-chat-dots-fill' : 'bi-chat-dots'))
</script>

<template>
  <TitlebarButton
    class="chat-bubble-toggle"
    :icon="icon"
    :tooltip="bubbleVisible ? t('agent.bubble.hide') : t('agent.bubble.show')"
    @click="toggleBubbleVisible"
  />
</template>

<style lang="scss" scoped>
/* Keep the 4px gap to the results button so the right-cluster icon spacing
   stays balanced (mirrors the results↔window-controls gap). */
.chat-bubble-toggle {
  margin-right: 4px;
}
</style>
