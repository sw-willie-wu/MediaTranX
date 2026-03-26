<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useConfirm } from '@/composables/useConfirm'
import { useI18n } from 'vue-i18n'

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
  removeSelected: [ids: string[]]
  clearSelection: []
  selectAll: []
}>()

// Ctrl+A → 全選, Delete → 移除
function handleKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
    if (props.items.length > 0) {
      e.preventDefault()
      emit('selectAll')
    }
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    if (props.items.length === 0) return
    e.preventDefault()
    handleDeleteKey()
  }
}

const { confirm: showConfirm } = useConfirm()
const { t } = useI18n()

async function handleDeleteKey() {
  const selectedCount = props.selectedIds.size
  if (selectedCount > 1) {
    const ok = await showConfirm({
      message: t('common.remove_selected_confirm', { count: selectedCount }),
      type: 'danger',
      confirmLabel: t('common.remove_file'),
    })
    if (ok) emit('removeSelected', [...props.selectedIds])
  } else if (props.activeId) {
    const ok = await showConfirm({
      message: t('common.remove_confirm'),
      type: 'danger',
      confirmLabel: t('common.remove_file'),
    })
    if (ok) emit('remove', props.activeId)
  }
}
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  document.addEventListener('mousedown', onGlobalMouseDown)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  document.removeEventListener('mousedown', onGlobalMouseDown)
})

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
    // 目前在框內或自動滾動累積的 → 選中
    if (dragHitIds.value.has(id)) return true
    // 曾被框碰過但現在不在框內 → 取消（即使原本是選中的）
    if (dragVisitedIds.value.has(id)) return false
    // 從沒被碰過 → 維持原始狀態
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
const dragHitIds = ref<Set<string>>(new Set())       // 目前應選中的（框內 + 自動滾動累積的）
const autoScrollHitIds = ref<Set<string>>(new Set())  // 因自動滾動被帶離框但仍應選中的
const dragVisitedIds = ref<Set<string>>(new Set())    // 曾被框碰過的（用於取消原始選取）
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
  startDragSelect(e)
}

function onGlobalMouseDown(e: MouseEvent) {
  if (!e.shiftKey || e.button !== 0) return
  // 如果在 filmstrip 內部點的，讓 onTrackMouseDown 處理
  const el = scrollEl.value
  if (el && el.contains(e.target as Node)) return
  startDragSelect(e)
}

function startDragSelect(e: MouseEvent) {
  e.preventDefault()
  selectionSnapshot = new Set(props.selectedIds)
  isDragSelecting.value = true
  dragHitIds.value = new Set()
  autoScrollHitIds.value = new Set()
  dragVisitedIds.value = new Set()
  dragStartVP.value   = { x: e.clientX, y: e.clientY }
  dragCurrentVP.value = { x: e.clientX, y: e.clientY }
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup',   onDragEnd)
}

let autoScrollInterval: ReturnType<typeof setInterval> | null = null

function onDragMove(e: MouseEvent) {
  if (!isDragSelecting.value) return
  dragCurrentVP.value = { x: e.clientX, y: e.clientY }
  const currentHits = new Set(computeHits())
  // 記錄曾被碰過的
  currentHits.forEach(id => dragVisitedIds.value.add(id))
  // 框內的 + 自動滾動累積的
  dragHitIds.value = new Set([...currentHits, ...autoScrollHitIds.value])

  // Auto-scroll filmstrip when drag cursor is near edges
  const el = scrollEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const edgeZone = 40
  const scrollSpeed = 8

  if (autoScrollInterval) {
    clearInterval(autoScrollInterval)
    autoScrollInterval = null
    // 停止自動滾動：累積的轉為「曾碰過的」，之後手動拖離就能取消
    autoScrollHitIds.value.forEach(id => dragVisitedIds.value.add(id))
    autoScrollHitIds.value = new Set()
  }

  const dragGoingLeft = e.clientX < dragStartVP.value.x
  const dragGoingRight = e.clientX >= dragStartVP.value.x

  if (e.clientX < rect.left + edgeZone && el.scrollLeft > 0) {
    // 反方向滾（拖往右但碰左邊緣）→ 清空累積，純滾動
    if (dragGoingRight) autoScrollHitIds.value = new Set()
    autoScrollInterval = setInterval(() => {
      computeHits().forEach(id => { if (dragGoingLeft) autoScrollHitIds.value.add(id) })
      el.scrollLeft -= scrollSpeed
      const current = new Set(computeHits())
      dragHitIds.value = new Set([...current, ...autoScrollHitIds.value])
    }, 16)
  } else if (e.clientX > rect.right - edgeZone && el.scrollLeft + el.clientWidth < el.scrollWidth) {
    if (dragGoingLeft) autoScrollHitIds.value = new Set()
    autoScrollInterval = setInterval(() => {
      computeHits().forEach(id => { if (dragGoingRight) autoScrollHitIds.value.add(id) })
      el.scrollLeft += scrollSpeed
      const current = new Set(computeHits())
      dragHitIds.value = new Set([...current, ...autoScrollHitIds.value])
    }, 16)
  }
}

function onDragEnd() {
  if (!isDragSelecting.value) return
  if (autoScrollInterval) { clearInterval(autoScrollInterval); autoScrollInterval = null }
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup',   onDragEnd)

  // 加上最後一刻的碰撞
  computeHits().forEach(id => { dragHitIds.value.add(id); dragVisitedIds.value.add(id) })
  // 合併：目前框選到的 + 原本選的（排除碰過又離開的）
  const merged = [
    ...dragHitIds.value,
    ...[...selectionSnapshot].filter(id => !dragVisitedIds.value.has(id)),
  ]
  autoScrollHitIds.value = new Set()
  dragVisitedIds.value = new Set()
  merged.forEach((id, i) => emit('select', id, i > 0))

  isDragSelecting.value = false
  dragHitIds.value = new Set()
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
  if (autoScrollInterval) clearInterval(autoScrollInterval)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="isDragSelecting && dragSelectStyle" class="filmstrip-drag-overlay" :style="dragSelectStyle" />
  </Teleport>
  <div class="app-filmstrip" :class="{ 'can-scroll-left': canScrollLeft, 'can-scroll-right': canScrollRight }">

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

  </div>
</template>

<style lang="scss" scoped>
.app-filmstrip {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 4px;
  min-height: 4.85rem;

  // Fade edges to hint scrollable content
  &::before,
  &::after {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    width: 48px;
    pointer-events: none;
    z-index: 2;
    transition: opacity 0.15s ease;
  }

  &::before {
    left: 0;
    background: linear-gradient(to right, var(--bg-gradient-end), transparent);
    opacity: 0;
  }

  &::after {
    right: 0;
    background: linear-gradient(to left, var(--bg-gradient-end), transparent);
    opacity: 0;
  }

  &.can-scroll-left::before { opacity: 1; }
  &.can-scroll-right::after { opacity: 1; }
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
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;

  &.is-active {
    border-color: var(--text-primary);
    box-shadow: 0 0 10px var(--filmstrip-glow-active);
  }

  &.is-selected:not(.is-active) {
    border-color: var(--color-accent);
    box-shadow: 0 0 8px var(--filmstrip-glow-selected);
    transform: scale(1.05);
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
