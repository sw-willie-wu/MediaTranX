<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { useAgent } from '@/composables/useAgent'
import { useBubbleDrag, BUBBLE_SIZE_PX, BUBBLE_MARGIN_PX } from '@/composables/useBubbleDrag'
import ChatHeader from './ChatHeader.vue'
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'

const store = useAgentStore()
const agent = useAgent()
const expanded = ref(false)

const { position, isDragging, bubbleStyle, onPointerDown } = useBubbleDrag()

function toggle() {
  expanded.value = !expanded.value
}

function onBubblePointerDown(e: PointerEvent) {
  onPointerDown(e, toggle)
}

/**
 * When expanded, the bubble flies up to a fixed top (EXPANDED_TOP_PX)
 * and the chat panel anchors next to it on the *inside* of the
 * viewport — bubble on the right edge → panel grows leftward from
 * just-left-of-bubble; bubble on the left edge → panel grows rightward
 * from just-right-of-bubble. Panel top aligns with bubble top so the
 * two feel like one composed widget.
 *
 * Clicking the bubble in expanded state closes the panel and the bubble
 * animates back to its drag-saved Y. The X close button on ChatHeader
 * was removed — the bubble is the only toggle.
 */
const EXPANDED_TOP_PX = BUBBLE_MARGIN_PX
const PANEL_WIDTH = 380
const PANEL_HEIGHT = 600
const PANEL_GAP_PX = 12

const bubbleStyleFinal = computed<Record<string, string>>(() => {
  const base = bubbleStyle.value
  if (expanded.value && !isDragging.value) {
    return { ...base, top: `${EXPANDED_TOP_PX}px` }
  }
  return base
})

const panelStyle = computed<Record<string, string>>(() => {
  const pos = position.value
  // Anchor panel adjacent to the bubble at its expanded position.
  // Right side: panel left of bubble. Left side: panel right of bubble.
  const sideRule = pos.side === 'right'
    ? { right: `${BUBBLE_MARGIN_PX + BUBBLE_SIZE_PX + PANEL_GAP_PX}px`, left: 'auto' }
    : { left: `${BUBBLE_MARGIN_PX + BUBBLE_SIZE_PX + PANEL_GAP_PX}px`, right: 'auto' }
  // Clamp panel so it never extends below viewport (corner case: very
  // short windows where viewport < EXPANDED_TOP_PX + PANEL_HEIGHT + MARGIN).
  const maxTop = Math.max(BUBBLE_MARGIN_PX, window.innerHeight - PANEL_HEIGHT - BUBBLE_MARGIN_PX)
  const top = Math.min(EXPANDED_TOP_PX, maxTop)
  return { ...sideRule, top: `${top}px`, bottom: 'auto' }
})

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && expanded.value) {
    expanded.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <!-- Bubble (always mounted, draggable, toggle on click). When
         expanded, it flies up to EXPANDED_TOP_PX and acts as the close
         button. -->
    <button
      class="chat-bubble-btn"
      :class="{ 'is-running': store.isRunning, 'is-dragging': isDragging, 'is-expanded': expanded }"
      :style="bubbleStyleFinal"
      @pointerdown="onBubblePointerDown"
      :aria-label="$t('agent.bubble.title')"
    >
      <i class="bi" :class="expanded ? 'bi-x-lg' : 'bi-robot'"></i>
      <span v-if="store.isRunning && !expanded" class="bubble-pulse"></span>
    </button>

    <!-- Panel (mounted only when expanded, anchored next to bubble) -->
    <div v-if="expanded" class="chat-bubble-panel" :style="panelStyle">
      <ChatHeader
        :token-usage="store.threadTokens"
        @clear="agent.clearHistory()"
      />
      <ChatMessages
        :messages="agent.messages.value"
        :transient="store.transient"
        :is-running="store.isRunning"
      />
      <ChatInput
        :disabled="store.isRunning"
        @send="agent.sendUserText"
        @cancel="agent.cancelRun()"
        :is-running="store.isRunning"
      />
    </div>
  </Teleport>
</template>

<style lang="scss" scoped>
.chat-bubble-btn {
  position: fixed;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--color-primary);
  border: none;
  color: white;
  font-size: 1.2rem;
  cursor: grab;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  z-index: 9000;
  transition: transform 0.2s ease-in-out, background 0.2s ease-in-out, top 0.25s ease-out, left 0.25s ease-out;
  touch-action: none; /* prevent browser pan/zoom during drag */
  /* The composable always emits `left: Npx; right: auto` (never the
     other way around) so CSS can transition `left` between any two
     positions — a side-toggling { right: 24, left: auto } ↔
     { left: 24, right: auto } scheme would teleport instead of
     animating because CSS can't ease between `auto` and a length.
     While dragging, useBubbleDrag overrides `transition: none` via
     inline style so the bubble follows the cursor without easing. */

  &:hover {
    background: var(--color-primary-hover);
    transform: scale(1.08);
  }

  &.is-running {
    background: var(--color-primary);
  }

  &.is-expanded {
    background: var(--color-primary-hover);
  }

  &.is-dragging {
    cursor: grabbing;
    transform: scale(1.05);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.32);
  }
}

.bubble-pulse {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-success);
  animation: pulse-ring 1.4s ease-out infinite;
}

@keyframes pulse-ring {
  0%   { transform: scale(0.9); opacity: 1; }
  70%  { transform: scale(1.3); opacity: 0.5; }
  100% { transform: scale(0.9); opacity: 1; }
}

.chat-bubble-panel {
  position: fixed;
  width: 380px;
  height: 600px;
  border-radius: 12px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  z-index: 9000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: panel-in 0.22s ease-out;
}

@keyframes panel-in {
  from { opacity: 0; transform: scale(0.96) translateY(-8px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}
</style>
