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

/**
 * Running-banner label. While the agent is between/before tool actions (e.g.
 * generating text) currentAction is empty → show the generic "working" label.
 * Once a tool dispatches, store.currentAction holds an `agent.banner.act.*` key
 * + args (set by useAgentTools), so the banner reads e.g. "Setting model = X".
 */
/**
 * Localize raw identifiers in an action's args before rendering, so the banner
 * shows human names instead of routes/ids. navigate_to's `route` (e.g. "/video")
 * → the localized domain name via `nav.*`. Other tools' args (panel field/option
 * ids, file ids, task ids) have no central translation map, so they pass through.
 */
function localizeActionArgs(key: string, args: Record<string, unknown>): Record<string, unknown> {
  if (key === 'agent.banner.act.navigate_to') {
    const word = String(args.route ?? '').trim().toLowerCase().replace(/^\/+/, '')
    const navKey = `nav.${word === '' ? 'home' : word}`
    const label = t(navKey)
    return { route: label === navKey ? String(args.route ?? '') : label }
  }
  return args
}

const bannerLabel = computed(() => {
  const ca = store.currentAction
  // A live tool action → show it; otherwise (streaming / a plain text reply
  // with no recognised action) the agent is thinking.
  return ca.key ? t(ca.key, localizeActionArgs(ca.key, ca.args)) : t('agent.bubble.thinking')
})

/** Collapse the panel back to the floating bubble. Shared by the Escape
 * key and the full-screen backdrop click. */
function collapse() {
  bubbleExpanded.value = false
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
    collapse()
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
    <!-- Full-screen backdrop. Shown when the panel is expanded (click-away to
         collapse) AND/OR while the agent is running — in the running case it
         keeps blocking the app even after the user collapses the chat, so the
         user can't fight the agent for the same panel state mid-run. Sits below
         the bubble/panel (z-index) so both stay interactive above it. -->
    <div
      v-if="bubbleExpanded || store.isRunning"
      class="chat-bubble-backdrop"
      :class="{ 'is-watch': store.isRunning && !bubbleExpanded }"
      @pointerdown="collapse"
      aria-hidden="true"
    ></div>

    <!-- Running banner: fixed top-centre pill shown while the agent runs but
         only when the chat is collapsed. When expanded, the panel itself shows
         progress (+ ChatInput has its own cancel), so the banner would just
         clutter the top alongside the panel and the X-bubble. Tapping the body
         opens the chat (e.g. to see/approve a pending confirm); the square stop
         button aborts the run. -->
    <div
      v-if="store.isRunning && !bubbleExpanded"
      class="agent-running-banner"
      role="status"
      @click="bubbleExpanded = true"
    >
      <span class="banner-label">{{ bannerLabel }}</span>
      <button
        class="banner-stop"
        @click.stop="agent.cancelRun()"
        :aria-label="$t('agent.bubble.abort')"
        :title="$t('agent.bubble.abort')"
      >
        <i class="bi bi-stop-fill"></i>
      </button>
    </div>

    <!-- Bubble (always mounted while visible, draggable, toggle on
         click). When expanded, it flies up to EXPANDED_TOP_PX and acts
         as the close button. -->
    <button
      class="chat-bubble-btn"
      :class="{
        'is-running': store.isRunning,
        'is-dragging': isDragging,
        'is-expanded': bubbleExpanded,
      }"
      :style="bubbleStyleFinal"
      @pointerdown="onBubblePointerDown"
      :aria-label="$t('agent.bubble.title')"
    >
      <i class="bi" :class="bubbleExpanded ? 'bi-x-lg' : 'bi-robot'"></i>
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

@property --beam-angle {
  syntax: '<angle>';
  initial-value: 0deg;
  inherits: false;
}

@keyframes beam-rotate {
  to { --beam-angle: 360deg; }
}

@media (prefers-reduced-motion: reduce) {
  .agent-running-banner::before { animation: none; }
}

.chat-bubble-backdrop {
  position: fixed;
  inset: 0;
  z-index: 8999; /* below bubble/panel (9000), above all app content */
  background: rgba(0, 0, 0, 0.18);
  cursor: default; /* it blocks the app — don't imply it's a click target */
  animation: backdrop-in 0.2s ease-out;

  /* Agent running while collapsed: keep blocking clicks but go transparent so
     the user can watch the agent manipulate panels live. The top banner already
     explains why the app is non-interactive. */
  &.is-watch {
    background: transparent;
  }
}

@keyframes backdrop-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.agent-running-banner {
  position: fixed;
  top: 68px; /* clear of the 40px titlebar drag zone AND offset from the
                panel's top edge (24px) so it doesn't sit flush with it */
  left: 50%;
  transform: translateX(-50%);
  z-index: 9500; /* above bubble/panel so the stop button is always reachable */
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 0.6rem 0.55rem 1.1rem;
  border-radius: 999px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  font-size: 0.92rem;
  color: var(--text-primary);
  cursor: default;
  /* Electron frameless: the 40px titlebar is a -webkit-app-region:drag zone.
     This pill sits at top:12px and overlaps it, so without no-drag the OS
     swallows hover/click as window-drag and the stop button is unreachable. */
  -webkit-app-region: no-drag;
  animation: banner-in 0.2s ease-out;

  /* Thin flowing border ring echoing the bubble. Muted lavender palette tuned
     to the theme primary (#7c6fad) so it harmonises with the bubble rather than
     clashing as a vivid cool ring. */
  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    padding: 1px;
    background: conic-gradient(
      from var(--beam-angle),
      #6366f1, #22d3ee, #a855f7, #38bdf8, #6366f1
    );
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor;
    mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    mask-composite: exclude; /* show only the ring */
    opacity: 0.6;
    pointer-events: none; /* decorative — never intercept clicks (mask hides it
                             visually but the full box still hit-tests) */
    animation: beam-rotate 3s linear infinite;
  }
}

.banner-label {
  font-weight: 500;
}

.banner-stop {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 50%;
  background: var(--input-bg);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.95rem;
  transition: background 0.15s ease, color 0.15s ease;

  &:hover {
    background: var(--color-danger);
    color: white;
  }
}

@keyframes banner-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-8px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
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
