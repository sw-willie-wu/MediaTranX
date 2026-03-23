<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

export interface FilmstripItem {
  id: string
  thumbnailUrl: string
  status: 'idle' | 'uploading' | 'processing' | 'done'
  progress: number
}

const props = withDefaults(
  defineProps<{
    items: FilmstripItem[]
    activeId: string | null
    selectedIds: Set<string>
  }>(),
  {
    activeId: null,
  },
)

const emit = defineEmits<{
  select: [id: string, ctrlKey: boolean]
  remove: [id: string]
  clearSelection: []
  selectAll: []
}>()

// Ctrl+A → 全選
function handleKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
    if (props.items.length > 0) {
      e.preventDefault()
      emit('selectAll')
    }
  }
}
onMounted(() => window.addEventListener('keydown', handleKeyDown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeyDown))

// --- Refs ---
const scrollEl = ref<HTMLElement | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)

const SCROLL_STEP = 200

// --- Scroll state ---
function updateScrollState() {
  const el = scrollEl.value
  if (!el) return
  canScrollLeft.value = el.scrollLeft > 0
  canScrollRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
}

function scrollLeft() {
  scrollEl.value?.scrollBy({ left: -SCROLL_STEP, behavior: 'smooth' })
}

function scrollRight() {
  scrollEl.value?.scrollBy({ left: SCROLL_STEP, behavior: 'smooth' })
}

function onWheel(e: WheelEvent) {
  const el = scrollEl.value
  if (!el) return
  e.preventDefault()
  el.scrollLeft += e.deltaY || e.deltaX
  updateScrollState()
}

function onScroll() {
  updateScrollState()
}

// --- Lifecycle ---
onMounted(() => {
  nextTick(updateScrollState)
})

watch(
  () => props.items,
  () => nextTick(updateScrollState),
  { deep: true },
)

// --- Helpers ---
function isActive(id: string) {
  return props.activeId === id
}

function isSelected(id: string) {
  if (isDragSelecting.value) {
    // 框碰過的：以目前是否在框內為準；從沒碰過的：維持 snapshot
    if (dragVisitedIds.value.has(id)) return dragHitIds.value.has(id)
    return selectionSnapshot.has(id)
  }
  return props.selectedIds.has(id)
}

function progressPct(item: FilmstripItem) {
  return Math.round(item.progress * 100)
}

// --- Shift+drag box select ---
const isDragSelecting = ref(false)
const justDragSelected = ref(false)
const dragStartVP = ref({ x: 0, y: 0 })   // viewport coords
const dragCurrentVP = ref({ x: 0, y: 0 })
const dragHitIds = ref<Set<string>>(new Set())
const dragVisitedIds = ref<Set<string>>(new Set())
let selectionSnapshot: Set<string> = new Set()

const dragSelectStyle = computed(() => {
  if (!isDragSelecting.value) return null
  const x1 = Math.min(dragStartVP.value.x, dragCurrentVP.value.x)
  const y1 = Math.min(dragStartVP.value.y, dragCurrentVP.value.y)
  const x2 = Math.max(dragStartVP.value.x, dragCurrentVP.value.x)
  const y2 = Math.max(dragStartVP.value.y, dragCurrentVP.value.y)
  return {
    left:   `${x1}px`,
    top:    `${y1}px`,
    width:  `${x2 - x1}px`,
    height: `${y2 - y1}px`,
  }
})

function computeHits(): string[] {
  if (!scrollEl.value) return []
  const selX1 = Math.min(dragStartVP.value.x, dragCurrentVP.value.x)
  const selY1 = Math.min(dragStartVP.value.y, dragCurrentVP.value.y)
  const selX2 = Math.max(dragStartVP.value.x, dragCurrentVP.value.x)
  const selY2 = Math.max(dragStartVP.value.y, dragCurrentVP.value.y)
  const itemEls = scrollEl.value.querySelectorAll<HTMLElement>('.filmstrip-item')
  const hit: string[] = []
  itemEls.forEach((el, i) => {
    const r = el.getBoundingClientRect()
    if (r.left < selX2 && r.right > selX1 && r.top < selY2 && r.bottom > selY1) {
      hit.push(props.items[i].id)
    }
  })
  return hit
}

function onTrackMouseDown(e: MouseEvent) {
  if (!e.shiftKey || e.button !== 0) return
  e.preventDefault()
  selectionSnapshot = new Set(props.selectedIds)
  isDragSelecting.value = true
  dragHitIds.value = new Set()
  dragVisitedIds.value = new Set()
  dragStartVP.value   = { x: e.clientX, y: e.clientY }
  dragCurrentVP.value = { x: e.clientX, y: e.clientY }
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup',   onDragEnd)
}

function onDragMove(e: MouseEvent) {
  if (!isDragSelecting.value) return
  dragCurrentVP.value = { x: e.clientX, y: e.clientY }
  const hits = new Set(computeHits())
  // 累積所有曾被框碰過的 id
  hits.forEach(id => dragVisitedIds.value.add(id))
  dragHitIds.value = hits
}

function onDragEnd() {
  if (!isDragSelecting.value) return
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup',   onDragEnd)

  const finalHits = new Set(computeHits())
  // snapshot 中「從沒被框碰過」的保留；「碰過但不在最終框內」的排除
  const merged = [
    ...[...selectionSnapshot].filter(id => !dragVisitedIds.value.has(id) || finalHits.has(id)),
    ...[...finalHits].filter(id => !selectionSnapshot.has(id)),
  ]
  merged.forEach((id, i) => emit('select', id, i > 0))

  isDragSelecting.value = false
  dragHitIds.value = new Set()
  dragVisitedIds.value = new Set()
  if (merged.length > 0) {
    justDragSelected.value = true
    setTimeout(() => { justDragSelected.value = false }, 0)
  }
}

function onTrackClick() {
  if (!justDragSelected.value) emit('clearSelection')
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup',   onDragEnd)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="isDragSelecting && dragSelectStyle" class="filmstrip-drag-overlay" :style="dragSelectStyle" />
  </Teleport>
  <div class="app-filmstrip">
    <!-- Left arrow -->
    <button
      class="filmstrip-arrow"
      :class="{ 'is-hidden': !canScrollLeft }"
      aria-label="Scroll left"
      @click="scrollLeft"
    >
      <i class="bi bi-chevron-left" />
    </button>

    <!-- Scroll track -->
    <div
      ref="scrollEl"
      class="filmstrip-track"
      :class="{ 'is-drag-selecting': isDragSelecting }"
      @scroll="onScroll"
      @wheel.passive="false"
      @wheel="onWheel"
      @mousedown="onTrackMouseDown"
      @click.self="onTrackClick"
    >
      <div
        v-for="item in items"
        :key="item.id"
        class="filmstrip-item"
        :class="{
          'is-active': isActive(item.id),
          'is-selected': isSelected(item.id),
        }"
        @click.exact="emit('select', item.id, false)"
        @click.ctrl.exact="emit('select', item.id, true)"
        @click.meta.exact="emit('select', item.id, true)"
      >
        <!-- Thumbnail image -->
        <img
          class="filmstrip-thumb"
          :src="item.thumbnailUrl"
          :alt="`Thumbnail ${item.id}`"
          draggable="false"
        />

        <!-- Status overlay: uploading -->
        <div v-if="item.status === 'uploading'" class="filmstrip-overlay">
          <i class="bi bi-arrow-clockwise filmstrip-spinner" />
        </div>

        <!-- Status overlay: processing -->
        <div v-else-if="item.status === 'processing'" class="filmstrip-overlay">
          <i class="bi bi-arrow-clockwise filmstrip-spinner" />
          <span class="filmstrip-progress-label">{{ progressPct(item) }}%</span>
        </div>

        <!-- Remove button (not shown while processing) -->
        <button
          v-if="item.status !== 'processing'"
          class="filmstrip-remove"
          aria-label="Remove"
          @click.stop="emit('remove', item.id)"
        >
          <i class="bi bi-x" />
        </button>
      </div>
    </div>

    <!-- Right arrow -->
    <button
      class="filmstrip-arrow"
      :class="{ 'is-hidden': !canScrollRight }"
      aria-label="Scroll right"
      @click="scrollRight"
    >
      <i class="bi bi-chevron-right" />
    </button>
  </div>
</template>

<style lang="scss" scoped>
.app-filmstrip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 4px;
  min-height: 4.85rem;
}

// ── Scroll track ────────────────────────────────────────────
.filmstrip-track {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 6px 0;
  scroll-behavior: auto; // smooth handled by scrollBy calls
  flex: 1;

  // Center items when few items (no overflow)
  &::before,
  &::after {
    content: '';
    flex: 1;
    min-width: 4px;
  }

  // Hide scrollbar visually but keep it functional
  scrollbar-width: none;
  &::-webkit-scrollbar {
    display: none;
  }
}

// ── Individual thumbnail item ────────────────────────────────
.filmstrip-item {
  position: relative;
  flex-shrink: 0;
  width: 72px;
  height: 60px;
  border-radius: 4px;
  overflow: visible; // allow remove btn to overflow
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;

  &.is-active {
    border-color: var(--text-primary);
    box-shadow: 0 0 10px var(--filmstrip-glow-active);
  }

  &.is-selected:not(.is-active) {
    border-color: var(--color-accent);
    box-shadow: 0 0 8px var(--filmstrip-glow-selected);
  }

  // Show remove button only on hover
  &:hover .filmstrip-remove {
    opacity: 1;
    pointer-events: auto;
  }
}

// ── Thumbnail image ──────────────────────────────────────────
.filmstrip-thumb {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 2px;
  background: var(--input-bg);
  user-select: none;
  -webkit-user-drag: none;
}

// ── Status overlay ───────────────────────────────────────────
.filmstrip-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  background: var(--modal-backdrop);
  border-radius: 2px;
  color: var(--text-primary);
  font-size: 0.7rem;
  pointer-events: none;
}

.filmstrip-spinner {
  font-size: 1rem;
  animation: filmstrip-spin 0.9s linear infinite;
}

.filmstrip-progress-label {
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1;
}

@keyframes filmstrip-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

// ── Remove button ────────────────────────────────────────────
.filmstrip-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  padding: 0;
  background: var(--color-danger);
  color: var(--text-primary);
  font-size: 0.75rem;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease, background 0.15s ease;

  &:hover {
    background: var(--color-danger-hover, color-mix(in srgb, var(--color-danger) 80%, black));
  }
}

// ── Drag-select cursor ───────────────────────────────────────
.filmstrip-track.is-drag-selecting {
  cursor: crosshair;
  user-select: none;
}

// ── Scroll arrows ─────────────────────────────────────────────
.filmstrip-arrow {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 44px;
  border: 1px solid var(--panel-border);
  border-radius: 4px;
  padding: 0;
  cursor: pointer;
  color: var(--text-primary);
  font-size: 0.9rem;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  transition: background 0.15s ease, border-color 0.15s ease, opacity 0.15s ease;

  &:hover {
    background: rgba(0, 0, 0, 0.55);
    border-color: var(--panel-border-hover);
  }

  &.is-hidden {
    opacity: 0;
    pointer-events: none;
  }
}
</style>

<style lang="scss">
// 選框 overlay（Teleport 到 body，不能用 scoped）
.filmstrip-drag-overlay {
  position: fixed;
  pointer-events: none;
  z-index: 9999;
  border: 1px solid var(--color-accent);
  background: var(--drag-over-bg);
  border-radius: 2px;
}
</style>
