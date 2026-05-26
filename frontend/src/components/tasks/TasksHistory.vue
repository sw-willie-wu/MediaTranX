<script setup lang="ts">
import { ref, computed, onMounted, onActivated } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiFetch } from '@/composables/useApi'
import { getTaskTypeLabel } from '@/utils/taskTypeLabel'

const { t } = useI18n()

interface HistoryItem {
  task_id: string
  task_type: string
  label: string | null
  file_name: string | null
  status: string
  error: string | null
  error_code: string | null
  result: Record<string, unknown> | null
  created_at: string
  completed_at: string
}

interface HistoryResponse {
  items: HistoryItem[]
  total: number
  page: number
  page_size: number
}

function getStatusLabel(status: string): string {
  const key = `tasks.history.${status}`
  const translated = t(key)
  return translated !== key ? translated : status
}

const items = ref<HistoryItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const loading = ref(false)
const loaded = ref(false)
const filterStatus = ref<string | null>(null)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

async function fetchHistory() {
  loading.value = true
  try {
    let url = `/tasks/history?page=${page.value}&page_size=${pageSize}`
    if (filterStatus.value) url += `&status=${filterStatus.value}`
    const resp = await apiFetch(url)
    if (resp.ok) {
      const data: HistoryResponse = await resp.json()
      items.value = data.items
      total.value = data.total
    }
  } catch (e) {
    console.error('Failed to fetch history:', e)
  } finally {
    loading.value = false
    loaded.value = true
  }
}

function setFilter(status: string | null) {
  filterStatus.value = status
  page.value = 1
  fetchHistory()
}

function goPage(p: number) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  fetchHistory()
}

async function deleteItem(taskId: string) {
  try {
    const resp = await apiFetch(`/tasks/history/${taskId}`, { method: 'DELETE' })
    if (resp.ok) {
      items.value = items.value.filter(i => i.task_id !== taskId)
      total.value--
    }
  } catch (e) {
    console.error('Failed to delete history item:', e)
  }
}

async function clearAll() {
  try {
    const resp = await apiFetch('/tasks/history', { method: 'DELETE' })
    if (resp.ok) {
      items.value = []
      total.value = 0
      page.value = 1
    }
  } catch (e) {
    console.error('Failed to clear history:', e)
  }
}

function taskLabel(item: HistoryItem): string {
  return item.label || getTaskTypeLabel(item.task_type)
}

function friendlyError(item: HistoryItem): string {
  if (item.error_code) {
    const key = `tasks.errors.${item.error_code}`
    const translated = t(key)
    if (translated !== key) return translated
  }
  // fallback: 截短原始錯誤
  return item.error ? (item.error.length > 100 ? item.error.slice(0, 100) + '...' : item.error) : ''
}

function fileName(item: HistoryItem): string | null {
  if (item.file_name) return item.file_name
  const fn = item.result?.output_filename as string | undefined
  return fn || null
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('zh-TW', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Human duration between created_at and completed_at, localized.
 *  <60s → "30s" / "30秒"
 *  <60m → "5m30s" / "5分30秒"
 *  ≥1h  → "1h23m45s" / "1時23分45秒" (full triple when hours present)
 *  Zero-valued lower units are omitted (e.g. "5m" not "5m0s").
 *  Returns '' when timestamps are missing/invalid so caller can hide gracefully.
 *  Unit suffixes come from i18n: tasks.history.duration_{h,m,s}. */
function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return ''
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (!Number.isFinite(ms) || ms < 0) return ''
  const totalSec = Math.round(ms / 1000)
  const sH = t('tasks.history.duration_h')
  const sM = t('tasks.history.duration_m')
  const sS = t('tasks.history.duration_s')

  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60

  if (h > 0) {
    let out = `${h}${sH}`
    if (m) out += `${m}${sM}`
    if (s) out += `${s}${sS}`
    return out
  }
  if (m > 0) {
    return s ? `${m}${sM}${s}${sS}` : `${m}${sM}`
  }
  return `${s}${sS}`
}

onMounted(() => fetchHistory())
onActivated(() => fetchHistory())
</script>

<template>
  <h6 class="section-title">{{ $t('tasks.history.title') }}</h6>

  <div class="history-toolbar">
    <div class="filter-bar">
      <button class="filter-chip" :class="{ 'is-active': filterStatus === null }" @click="setFilter(null)">{{ $t('tasks.history.all') }}</button>
      <button class="filter-chip" :class="{ 'is-active': filterStatus === 'completed' }" @click="setFilter('completed')">{{ $t('tasks.history.completed') }}</button>
      <button class="filter-chip" :class="{ 'is-active': filterStatus === 'failed' }" @click="setFilter('failed')">{{ $t('tasks.history.failed') }}</button>
      <button class="filter-chip" :class="{ 'is-active': filterStatus === 'cancelled' }" @click="setFilter('cancelled')">{{ $t('tasks.history.cancelled') }}</button>
    </div>
    <button v-if="items.length > 0" class="clear-btn" @click="clearAll">
      <i class="bi bi-trash3"></i>
      {{ $t('tasks.history.clear') }}
    </button>
  </div>

  <div v-if="loading && items.length === 0" class="loading-state">
    <div class="spinner-sm"></div>
  </div>

  <div v-else-if="items.length === 0" class="empty-state">
    <i class="bi bi-inbox"></i>
    <p>{{ $t('tasks.history.empty') }}</p>
  </div>

  <div v-else class="task-list">
    <div v-for="item in items" :key="item.task_id" class="task-card">
      <div class="task-header">
        <div class="task-title">
          <span class="task-label">{{ taskLabel(item) }}</span>
          <span v-if="fileName(item)" class="task-filename">{{ fileName(item) }}</span>
        </div>
        <span class="task-badge" :class="`badge-${item.status}`">
          {{ getStatusLabel(item.status) }}
        </span>
      </div>
      <div v-if="item.status === 'failed' && item.error" class="task-error">
        <div class="error-info">
          <i class="bi bi-exclamation-circle-fill"></i>
          <span>{{ friendlyError(item) }}</span>
        </div>
      </div>
      <div class="task-footer">
        <div class="task-times">
          <span class="task-time">
            <span class="time-label">{{ $t('tasks.history.completed_at') }}</span>
            {{ formatDate(item.completed_at) }}
          </span>
          <span v-if="formatDuration(item.created_at, item.completed_at)" class="task-time">
            <span class="time-label">{{ $t('tasks.history.duration') }}</span>
            {{ formatDuration(item.created_at, item.completed_at) }}
          </span>
        </div>
        <button class="remove-btn show-on-hover" @click="deleteItem(item.task_id)">
          <i class="bi bi-trash3"></i>
        </button>
      </div>
    </div>
  </div>

  <div v-if="totalPages > 1" class="pagination">
    <button class="page-btn" :disabled="page <= 1" @click="goPage(page - 1)">
      <i class="bi bi-chevron-left"></i>
    </button>
    <span class="page-info">{{ page }} / {{ totalPages }}</span>
    <button class="page-btn" :disabled="page >= totalPages" @click="goPage(page + 1)">
      <i class="bi bi-chevron-right"></i>
    </button>
  </div>
</template>

<style lang="scss" scoped>
.section-title {
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 1rem;
  color: var(--text-muted);

  i { font-size: 3rem; margin-bottom: 1rem; opacity: 0.5; }
  p { font-size: 0.95rem; margin: 0; }
}

.history-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.filter-bar {
  display: flex;
  gap: 0.4rem;
}

.filter-chip {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.78rem;
  padding: 0.25rem 0.6rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &.is-active {
    background: color-mix(in srgb, var(--color-accent) 15%, transparent);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }

  &:hover:not(.is-active) {
    border-color: var(--panel-border-hover);
    color: var(--text-primary);
  }
}

.clear-btn {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  background: none;
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  color: var(--text-muted);
  font-size: 0.78rem;
  padding: 0.25rem 0.6rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    color: var(--color-danger);
    border-color: var(--color-danger);
  }
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.task-card {
  padding: 14px 16px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.task-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.task-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.task-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-primary);
}

.task-filename {
  font-size: 0.78rem;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-badge {
  flex-shrink: 0;
  font-size: 0.72rem;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 6px;

  &.badge-completed {
    background: color-mix(in srgb, var(--color-success) 15%, transparent);
    color: var(--color-success);
  }

  &.badge-failed {
    background: color-mix(in srgb, var(--color-danger) 15%, transparent);
    color: var(--color-danger);
  }

  &.badge-cancelled {
    background: color-mix(in srgb, var(--text-muted) 15%, transparent);
    color: var(--text-muted);
  }
}

.task-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 4px;

  .error-info {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.8rem;
    color: var(--color-danger);
    min-width: 0;

    i { flex-shrink: 0; font-size: 0.85rem; }
    span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  }
}

.task-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.task-times {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.task-time {
  font-size: 0.72rem;
  color: var(--text-muted);
  opacity: 0.7;
}

.time-label {
  margin-right: 0.25rem;
  opacity: 0.7;
}

.remove-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  flex-shrink: 0;

  i { font-size: 0.85rem; }
  &:hover { color: var(--color-danger); }

  &.show-on-hover {
    opacity: 0;
    .task-card:hover & { opacity: 1; }
  }
}

.loading-state {
  display: flex;
  justify-content: center;
  padding: 4rem 0;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 1.5rem 0 0.5rem;
}

.page-btn {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover:not(:disabled) {
    border-color: var(--panel-border-hover);
    color: var(--text-primary);
  }

  &:disabled { opacity: 0.3; cursor: not-allowed; }
}

.page-info {
  font-size: 0.82rem;
  color: var(--text-muted);
}

.spinner-sm {
  width: 20px;
  height: 20px;
  border: 2px solid var(--panel-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
