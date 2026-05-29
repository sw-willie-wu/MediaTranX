<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAgentStore } from '@/stores/agent'
import { useAgent } from '@/composables/useAgent'
import { useBubbleDrag, BUBBLE_SIZE_PX, BUBBLE_EDGE_PX, BUBBLE_MARGIN_PX } from '@/composables/useBubbleDrag'
import { bubbleVisible, bubbleExpanded } from '@/composables/useBubbleVisibility'
import { useToast } from '@/composables/useToast'
import ChatHeader from './ChatHeader.vue'
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'
import SessionList from './SessionList.vue'

const store = useAgentStore()
const agent = useAgent()

const view = ref<'list' | 'chat'>('chat')   // ChatBubble-local; survives collapse/reopen within a run
const { t } = useI18n()
const { show } = useToast()

async function onSelectSession(id: string) {
  try {
    await agent.loadSession(id)
    view.value = 'chat'
  } catch {
    show(t('agent.session.load_failed'), { type: 'error' })
  }
}

function onNewChat() {
  agent.startNewSession()
  view.value = 'chat'
}

const { position, isDragging, bubbleStyle, onPointerDown } = useBubbleDrag()

function toggle() {
  bubbleExpanded.value = !bubbleExpanded.value
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
const PANEL_GAP_PX = 12

const bubbleStyleFinal = computed<Record<string, string | undefined>>(() => {
  const base = bubbleStyle.value
  if (bubbleExpanded.value && !isDragging.value) {
    return { ...base, top: `${EXPANDED_TOP_PX}px` }
  }
  return base
})

const panelStyle = computed<Record<string, string>>(() => {
  const pos = position.value
  // Anchor panel adjacent to the bubble at its expanded position.
  // Right side: panel left of bubble. Left side: panel right of bubble.
  // Offset = viewport-edge gap + bubble width + bubble↔panel gap.
  const adjacentOffset = BUBBLE_EDGE_PX + BUBBLE_SIZE_PX + PANEL_GAP_PX
  const sideRule = pos.side === 'right'
    ? { right: `${adjacentOffset}px`, left: 'auto' }
    : { left: `${adjacentOffset}px`, right: 'auto' }
  // Full-height: anchor both top and bottom so the panel stretches
  // between them. Browser resolves the panel height automatically;
  // the .chat-bubble-panel CSS uses `height: auto` so this works.
  return {
    ...sideRule,
    top: `${EXPANDED_TOP_PX}px`,
    bottom: `${BUBBLE_MARGIN_PX}px`,
  }
})

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && bubbleExpanded.value) {
    bubbleExpanded.value = false
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
    <!-- Whole widget gated by the titlebar toggle (default: hidden).
         When bubbleVisible is false, neither the floating bubble button
         nor the expanded panel renders; the user controls visibility
         from the Titlebar chat_bubble icon. -->
    <template v-if="bubbleVisible">
    <!-- Bubble (always mounted while visible, draggable, toggle on
         click). When expanded, it flies up to EXPANDED_TOP_PX and acts
         as the close button. -->
    <button
      class="chat-bubble-btn"
      :class="{ 'is-running': store.isRunning, 'is-dragging': isDragging, 'is-expanded': bubbleExpanded }"
      :style="bubbleStyleFinal"
      @pointerdown="onBubblePointerDown"
      :aria-label="$t('agent.bubble.title')"
    >
      <i class="bi" :class="bubbleExpanded ? 'bi-x-lg' : 'bi-robot'"></i>
      <span v-if="store.isRunning && !bubbleExpanded" class="bubble-pulse"></span>
    </button>

    <!-- Panel (mounted only when expanded, anchored next to bubble) -->
    <div v-if="bubbleExpanded" class="chat-bubble-panel" :style="panelStyle">
      <SessionList
        v-if="view === 'list'"
        @select="onSelectSession"
        @new-chat="onNewChat"
      />
      <template v-else>
        <ChatHeader
          :token-usage="store.threadTokens"
          @back="view = 'list'"
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
      </template>
    </div>
    </template>
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
  height: auto; /* stretches between :style top and bottom */
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
