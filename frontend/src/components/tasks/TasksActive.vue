<script setup lang="ts">
import { onMounted, onActivated, computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/tasks'
import ProgressBar from '@/components/common/ProgressBar.vue'
import { getTaskTypeLabel } from '@/utils/taskTypeLabel'

const { t } = useI18n()
const taskStore = useTaskStore()

const activeTasks = computed(() =>
  [...taskStore.allTasks]
    .filter(t => t.status === 'pending' || t.status === 'processing')
    .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())
)

function statusLabel(status: string) {
  return status === 'pending' ? t('tasks.active.pending') : t('tasks.active.processing')
}

function translateProgress(message: string | null): string | undefined {
  if (!message) return undefined
  if (!message.startsWith('task.progress.')) return message
  const parts = message.split('|')
  const key = parts[0]
  if (parts.length === 1) return t(key)
  const params = parts.slice(1)
  return t(key, params)
}

function formatTime(date: Date) {
  return date.toLocaleTimeString('zh-TW', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const cancelling = ref<Set<string>>(new Set())

async function handleCancel(taskId: string) {
  cancelling.value.add(taskId)
  await taskStore.cancelTask(taskId)
  cancelling.value.delete(taskId)
}

onMounted(() => taskStore.refreshTasks())
onActivated(() => taskStore.refreshTasks())
</script>

<template>
  <h6 class="section-title">{{ $t('tasks.active.title') }}</h6>

  <div v-if="activeTasks.length === 0" class="empty-state">
    <i class="bi bi-inbox"></i>
    <p>{{ $t('tasks.active.empty') }}</p>
  </div>

  <TransitionGroup v-else name="task-list" tag="div" class="task-list">
    <div v-for="task in activeTasks" :key="task.taskId" class="task-card">
      <div class="task-header">
        <div class="task-title">
          <span class="task-label">{{ task.label ?? getTaskTypeLabel(task.taskType) }}</span>
          <span v-if="task.fileName" class="task-filename">{{ task.fileName }}</span>
        </div>
        <span class="task-badge" :class="`badge-${task.status}`">
          {{ statusLabel(task.status) }}
        </span>
      </div>
      <div class="task-progress">
        <ProgressBar :progress="task.progress" :message="translateProgress(task.message)" :show-percentage="true" />
      </div>
      <div class="task-footer">
        <span class="task-time">{{ formatTime(task.createdAt) }}</span>
        <button
          class="cancel-btn"
          :disabled="cancelling.has(task.taskId)"
          @click="handleCancel(task.taskId)"
        >
          <i class="bi bi-x-circle"></i>{{ $t('tasks.active.cancel') }}
        </button>
      </div>
    </div>
  </TransitionGroup>
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
  min-height: calc(100vh - 200px);
  color: var(--text-muted);

  i { font-size: 3rem; margin-bottom: 1rem; opacity: 0.5; }
  p { font-size: 0.95rem; margin: 0; }
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

  &.badge-pending {
    background: color-mix(in srgb, var(--color-warning) 15%, transparent);
    color: var(--color-warning);
  }

  &.badge-processing {
    background: color-mix(in srgb, var(--color-info) 15%, transparent);
    color: var(--color-info);
  }
}

.task-progress { margin-bottom: 4px; }

.task-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.task-time {
  font-size: 0.72rem;
  color: var(--text-muted);
  opacity: 0.7;
}

.cancel-btn {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  background: none;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.75rem;
  padding: 0.2rem 0.5rem;
  cursor: pointer;
  transition: all 0.15s ease;

  i { font-size: 0.78rem; }

  &:hover {
    color: var(--color-danger);
    border-color: var(--color-danger);
  }

  &:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
}

.task-list-enter-active { transition: all 0.2s ease; }
.task-list-leave-active { transition: all 0.2s ease; }
.task-list-enter-from { opacity: 0; transform: translateY(-10px); }
.task-list-leave-to { opacity: 0; transform: translateX(20px); }
.task-list-move { transition: transform 0.2s ease; }
</style>
