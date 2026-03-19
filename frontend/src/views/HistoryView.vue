<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/composables/useApi'

interface HistoryItem {
  task_id: string
  task_type: string
  label: string | null
  file_name: string | null
  status: string
  error: string | null
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

const TASK_TYPE_LABELS: Record<string, string> = {
  'image.upscale': '圖片超解析',
  'image.compress': '圖片壓縮',
  'image.convert': '圖片轉檔',
  'image.filter': '圖片濾鏡',
  'image.crop': '圖片裁切',
  'image.remove_bg': '圖片去背',
  'image.remove_object': '物件移除',
  'image.ocr': '圖片文字辨識',
  'video.transcode': '影片轉檔',
  'video.cut': '影片剪輯',
  'video.extract_audio': '音軌提取',
  'video.subtitle_generate': '字幕產生',
  'audio.transcode': '音訊轉檔',
  'audio.cut': '音訊剪輯',
  'audio.volume': '音量調整',
  'audio.transcribe': '語音轉文字',
  'document.ocr': '文件辨識',
  'document.translate': '文件翻譯',
  'document.pdf_convert': 'PDF 轉換',
  'document.split': '文件分割',
  'setup.model_download': '模型下載',
  'ai.setup': 'AI 環境初始化',
}

const STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '失敗',
  cancelled: '已取消',
}

const items = ref<HistoryItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const loading = ref(false)
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
  return item.label || TASK_TYPE_LABELS[item.task_type] || item.task_type
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

onMounted(fetchHistory)
</script>

<template>
  <div class="history-page">
    <div class="history-container">
      <div class="page-header">
        <h2 class="page-title">
          <i class="bi bi-clock-history"></i>
          歷史紀錄
        </h2>
        <button
          v-if="items.length > 0"
          class="clear-btn"
          @click="clearAll"
        >
          <i class="bi bi-trash3"></i>
          清空
        </button>
      </div>

      <!-- 篩選 -->
      <div class="filter-bar">
        <button
          class="filter-chip"
          :class="{ 'is-active': filterStatus === null }"
          @click="setFilter(null)"
        >全部</button>
        <button
          class="filter-chip"
          :class="{ 'is-active': filterStatus === 'completed' }"
          @click="setFilter('completed')"
        >已完成</button>
        <button
          class="filter-chip"
          :class="{ 'is-active': filterStatus === 'failed' }"
          @click="setFilter('failed')"
        >失敗</button>
        <button
          class="filter-chip"
          :class="{ 'is-active': filterStatus === 'cancelled' }"
          @click="setFilter('cancelled')"
        >已取消</button>
      </div>

      <!-- 載入中 -->
      <div v-if="loading && items.length === 0" class="loading-state">
        <div class="spinner-sm"></div>
      </div>

      <!-- 空狀態 -->
      <div v-else-if="items.length === 0" class="empty-state">
        <i class="bi bi-inbox"></i>
        <p>尚無歷史紀錄</p>
      </div>

      <!-- 歷史列表 -->
      <div v-else class="history-list">
        <div
          v-for="item in items"
          :key="item.task_id"
          class="history-card glass-card"
        >
          <div class="card-header">
            <div class="card-title">
              <span class="card-label">{{ taskLabel(item) }}</span>
              <span v-if="fileName(item)" class="card-filename">{{ fileName(item) }}</span>
            </div>
            <span class="card-badge" :class="`badge-${item.status}`">
              {{ STATUS_LABELS[item.status] || item.status }}
            </span>
          </div>
          <div v-if="item.status === 'failed' && item.error" class="card-error">
            <i class="bi bi-exclamation-circle-fill"></i>
            <span>{{ item.error }}</span>
          </div>
          <div class="card-footer">
            <span class="card-time">{{ formatDate(item.completed_at) }}</span>
            <button class="remove-btn" @click="deleteItem(item.task_id)">
              <i class="bi bi-trash3"></i>
            </button>
          </div>
        </div>
      </div>

      <!-- 分頁 -->
      <div v-if="totalPages > 1" class="pagination">
        <button
          class="page-btn"
          :disabled="page <= 1"
          @click="goPage(page - 1)"
        >
          <i class="bi bi-chevron-left"></i>
        </button>
        <span class="page-info">{{ page }} / {{ totalPages }}</span>
        <button
          class="page-btn"
          :disabled="page >= totalPages"
          @click="goPage(page + 1)"
        >
          <i class="bi bi-chevron-right"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.history-page {
  display: flex;
  justify-content: center;
  min-height: calc(100vh - 40px);
  padding: 2rem 1rem;
}

.history-container {
  width: 100%;
  max-width: 640px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.3rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;

  i { font-size: 1.2rem; }
}

.clear-btn {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  background: none;
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  color: var(--text-muted);
  font-size: 0.78rem;
  padding: 0.3rem 0.6rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    color: var(--color-danger);
    border-color: var(--color-danger);
  }
}

.filter-bar {
  display: flex;
  gap: 0.4rem;
  margin-bottom: 1.25rem;
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
    background: rgba(168, 156, 200, 0.15);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }

  &:hover:not(.is-active) {
    border-color: var(--panel-border-hover);
    color: var(--text-primary);
  }
}

.loading-state {
  display: flex;
  justify-content: center;
  padding: 4rem 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 1rem;
  color: var(--text-muted);

  i {
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: 0.5;
  }

  p {
    font-size: 0.95rem;
    margin: 0;
  }
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.glass-card {
  background: var(--panel-bg);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.history-card {
  padding: 14px 16px;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.card-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.card-label {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary);
}

.card-filename {
  font-size: 0.78rem;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-badge {
  flex-shrink: 0;
  font-size: 0.72rem;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 6px;

  &.badge-completed {
    background: rgba(52, 211, 153, 0.15);
    color: var(--color-success);
  }

  &.badge-failed {
    background: rgba(248, 113, 113, 0.15);
    color: var(--color-danger);
  }

  &.badge-cancelled {
    background: rgba(156, 163, 175, 0.15);
    color: var(--text-muted);
  }
}

.card-error {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--color-danger);
  margin-bottom: 4px;

  i { flex-shrink: 0; font-size: 0.82rem; }
  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-time {
  font-size: 0.72rem;
  color: var(--text-muted);
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
  transition: color 0.15s ease;
  opacity: 0;

  .history-card:hover & { opacity: 1; }

  i { font-size: 0.82rem; }

  &:hover { color: var(--color-danger); }
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

  &:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
}

.page-info {
  font-size: 0.82rem;
  color: var(--text-muted);
}

.spinner-sm {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-color);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
