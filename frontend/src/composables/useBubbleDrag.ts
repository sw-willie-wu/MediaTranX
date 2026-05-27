/**
 * Drag-and-snap support for the ChatBubble.
 *
 * Exposes:
 *   - pure helpers (snapSide, clampY, load/save) tested in
 *     __tests__/bubbleDrag.test.ts
 *   - useBubbleDrag() composable that wires pointer events on the
 *     bubble button, tracks click-vs-drag, snaps to the nearest side
 *     on release, and persists the result to localStorage.
 *
 * User-facing rules:
 *   - bubble center on left half → snap left; right half → snap right
 *   - exactly at midpoint → snap right (user tie-breaker)
 *   - bubble Y preserved on snap, clamped to viewport
 *   - drag delta < CLICK_THRESHOLD_PX is treated as a click, not a drag
 *   - position persisted as { side, y } in localStorage
 */

import { ref, computed, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'

export type BubbleSide = 'left' | 'right'

export interface BubblePosition {
  side: BubbleSide
  y: number
}

// Bubble button geometry (must match ChatBubble.vue CSS).
export const BUBBLE_SIZE_PX = 48
export const BUBBLE_MARGIN_PX = 24
const CLICK_THRESHOLD_PX = 5
const LS_KEY = 'chat-bubble-position'

// Fallback when nothing is persisted: bottom-right, ~24px above the
// viewport bottom. The y here is a sentinel — useBubbleDrag() recomputes
// it from window.innerHeight when the composable mounts so the bubble
// lands at the same on-screen spot as the pre-drag default.
export const DEFAULT_BUBBLE_POSITION: BubblePosition = { side: 'right', y: 0 }

// ── Pure helpers (tested) ─────────────────────────────────────────────────

/**
 * Snap to the nearer side based on the bubble's CENTER X (not its left
 * edge). Tie at the exact midpoint goes to 'right' per the user spec.
 */
export function snapSide(bubbleLeft: number, viewportWidth: number): BubbleSide {
  const centerX = bubbleLeft + BUBBLE_SIZE_PX / 2
  return centerX < viewportWidth / 2 ? 'left' : 'right'
}

/**
 * Clamp a bubble Y into the viewport, leaving BUBBLE_MARGIN_PX gap on
 * both top and bottom.
 */
export function clampY(y: number, viewportHeight: number): number {
  const minY = BUBBLE_MARGIN_PX
  const maxY = viewportHeight - BUBBLE_SIZE_PX - BUBBLE_MARGIN_PX
  return Math.max(minY, Math.min(maxY, y))
}

/**
 * Load persisted position from localStorage. Returns DEFAULT on any
 * shape mismatch (missing, malformed JSON, bad side, non-finite y).
 */
export function loadBubblePosition(): BubblePosition {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return DEFAULT_BUBBLE_POSITION
    const parsed = JSON.parse(raw)
    if (parsed?.side !== 'left' && parsed?.side !== 'right') return DEFAULT_BUBBLE_POSITION
    if (typeof parsed.y !== 'number' || !Number.isFinite(parsed.y)) return DEFAULT_BUBBLE_POSITION
    return { side: parsed.side, y: parsed.y }
  } catch {
    return DEFAULT_BUBBLE_POSITION
  }
}

export function saveBubblePosition(pos: BubblePosition): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(pos))
  } catch {
    // localStorage can throw under quota or private-mode — silently
    // ignore; the in-memory position still works for this session.
  }
}

// ── Composable (wires pointer events) ─────────────────────────────────────

export interface BubbleDragApi {
  /** Current snapped position (or in-flight drag position if dragging). */
  position: Ref<BubblePosition>
  /** True while the user is actively dragging (delta passed threshold). */
  isDragging: Ref<boolean>
  /**
   * Inline style for the bubble button. Uses `top` + `left`/`right`
   * depending on the snapped side. While dragging, uses absolute
   * `top` + `left` from the cursor.
   */
  bubbleStyle: ComputedRef<Record<string, string>>
  /**
   * Attach to the bubble button's pointerdown. Starts tracking and, on
   * pointerup, either snaps + persists (if dragged) or invokes
   * onClickFallback (if delta stayed under threshold).
   */
  onPointerDown: (e: PointerEvent, onClickFallback: () => void) => void
}

export function useBubbleDrag(): BubbleDragApi {
  // Initial position. Y default snaps the bubble to the bottom-right
  // exactly where it sat before drag-and-snap existed.
  const initial = loadBubblePosition()
  if (initial === DEFAULT_BUBBLE_POSITION) {
    initial.y = Math.max(BUBBLE_MARGIN_PX, window.innerHeight - BUBBLE_SIZE_PX - BUBBLE_MARGIN_PX)
  }

  const position = ref<BubblePosition>(initial)
  const isDragging = ref(false)
  // Viewport dims kept reactive so the right-side `left` px below
  // refreshes when the window resizes (computed re-evaluates).
  const viewportWidth = ref(window.innerWidth)
  const viewportHeight = ref(window.innerHeight)

  // In-flight drag state — raw cursor-anchored coordinates, ignored
  // by the snap logic until pointerup.
  const dragX = ref(0)
  const dragY = ref(0)

  // Internal: track delta to distinguish click vs drag.
  let startX = 0
  let startY = 0
  let bubbleStartLeft = 0  // bubble's left edge at pointerdown (in px)
  let bubbleStartTop = 0   // bubble's top edge at pointerdown
  let pendingClickFallback: (() => void) | null = null

  const bubbleStyle = computed<Record<string, string>>(() => {
    if (isDragging.value) {
      return {
        left: `${dragX.value}px`,
        top: `${dragY.value}px`,
        right: 'auto',
        bottom: 'auto',
        // No transition while dragging — must follow cursor 1:1.
        transition: 'none',
      }
    }
    // Always emit `left: Npx; right: auto` (never `right: 24px; left: auto`).
    // CSS cannot transition between `auto` and a length, so toggling
    // anchor sides would make the snap-right case teleport instead of
    // animating. Computing `left` from viewport width keeps both sides
    // on the same transitionable property.
    const pos = position.value
    const leftPx = pos.side === 'right'
      ? viewportWidth.value - BUBBLE_SIZE_PX - BUBBLE_MARGIN_PX
      : BUBBLE_MARGIN_PX
    return {
      left: `${leftPx}px`,
      right: 'auto',
      top: `${pos.y}px`,
      bottom: 'auto',
    }
  })

  function onPointerMove(e: PointerEvent) {
    const dx = e.clientX - startX
    const dy = e.clientY - startY
    const totalDelta = Math.hypot(dx, dy)
    if (!isDragging.value && totalDelta < CLICK_THRESHOLD_PX) return
    if (!isDragging.value) isDragging.value = true
    dragX.value = bubbleStartLeft + dx
    dragY.value = bubbleStartTop + dy
  }

  function onPointerUp(e: PointerEvent) {
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)

    if (!isDragging.value) {
      // Treat as click — fire the fallback (toggle expanded).
      pendingClickFallback?.()
      pendingClickFallback = null
      return
    }

    // Snap to nearest side based on the final cursor-anchored position.
    const finalLeft = bubbleStartLeft + (e.clientX - startX)
    const finalTop = bubbleStartTop + (e.clientY - startY)
    const snapped: BubblePosition = {
      side: snapSide(finalLeft, window.innerWidth),
      y: clampY(finalTop, window.innerHeight),
    }
    position.value = snapped
    saveBubblePosition(snapped)
    isDragging.value = false
    pendingClickFallback = null
  }

  function onPointerDown(e: PointerEvent, onClickFallback: () => void) {
    // Left button only.
    if (e.button !== 0) return
    e.preventDefault()
    startX = e.clientX
    startY = e.clientY
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    bubbleStartLeft = rect.left
    bubbleStartTop = rect.top
    pendingClickFallback = onClickFallback
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
  }

  // Reclamp Y on viewport resize so a previously-stored bottom position
  // doesn't push the bubble offscreen on a shorter window. Also refresh
  // viewport ref so the right-side `left` px in bubbleStyle reflows.
  function onResize() {
    viewportWidth.value = window.innerWidth
    viewportHeight.value = window.innerHeight
    const reclamped = clampY(position.value.y, window.innerHeight)
    if (reclamped !== position.value.y) {
      position.value = { ...position.value, y: reclamped }
      saveBubblePosition(position.value)
    }
  }

  onMounted(() => {
    window.addEventListener('resize', onResize)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('resize', onResize)
    // Defensive: tear down any in-flight drag listeners on unmount.
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)
  })

  return { position, isDragging, bubbleStyle, onPointerDown }
}
