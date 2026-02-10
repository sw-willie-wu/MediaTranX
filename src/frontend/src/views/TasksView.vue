<script setup lang="ts">
import { onMounted, onActivated, computed } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import ProgressBar from '@/components/common/ProgressBar.vue'

const taskStore = useTaskStore()

const sortedTasks = computed(() =>
  [...taskStore.allTasks].sort(
    (a, b) => b.createdAt.getTime() - a.createdAt.getTime()
  )
)

function statusLabel(status: string) {
  switch (status) {
    case 'pending': return '等待中'
    case 'processing': return '進行中'
    case 'completed': return '已完成'
    case 'failed': return '失敗'
    case 'cancelled': return '已取消'
    default: return status
  }
}

function formatTime(date: Date) {
  return date.toLocaleTimeString('zh-TW', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function handleRemove(taskId: string) {
  taskStore.removeTask(taskId)
}

onMounted(() => {
  taskStore.refreshTasks()
})

onActivated(() => {
  taskStore.refreshTasks()
})
</script>

<template>
  <div class="tasks-page">
    <div class="tasks-container">
      <h2 class="page-title">
        <i class="bi bi-list-task"></i>
        執行任務
      </h2>

      <!-- 空狀態 -->
      <div v-if="sortedTasks.length === 0" class="empty-state">
        <i class="bi bi-inbox"></i>
        <p>目前沒有任務</p>
      </div>

      <!-- 任務列表 -->
      <TransitionGroup name="task-list" tag="div" class="task-list">
        <div
          v-for="task in sortedTasks"
          :key="task.taskId"
          class="task-card glass-card"
        >
          <div class="task-header">
            <div class="task-title">
              <span class="task-label">{{ task.label ?? task.taskType }}</span>
              <span v-if="task.fileName" class="task-filename">{{ task.fileName }}</span>
            </div>
            <span class="task-badge" :class="`badge-${task.status}`">
              {{ statusLabel(task.status) }}
            </span>
          </div>

          <!-- 進行中 -->
          <div v-if="task.status === 'processing' || task.status === 'pending'" class="task-progress">
            <ProgressBar
              :progress="task.progress"
              :message="task.message ?? undefined"
              :show-percentage="true"
            />
          </div>

          <!-- 已完成 -->
          <div v-else-if="task.status === 'completed'" class="task-done">
            <i class="bi bi-check-circle-fill"></i>
            <span>{{ formatTime(task.updatedAt) }} 完成</span>
          </div>

          <!-- 失敗 -->
          <div v-else-if="task.status === 'failed'" class="task-error">
            <div class="error-info">
              <i class="bi bi-exclamation-circle-fill"></i>
              <span>{{ task.error ?? '未知錯誤' }}</span>
            </div>
            <button class="remove-btn" @click="handleRemove(task.taskId)">
              <i class="bi bi-trash3"></i>
            </button>
          </div>

          <!-- 已取消 -->
          <div v-else-if="task.status === 'cancelled'" class="task-cancelled">
            <i class="bi bi-dash-circle"></i>
            <span>已取消</span>
            <button class="remove-btn" @click="handleRemove(task.taskId)">
              <i class="bi bi-trash3"></i>
            </button>
          </div>

          <div class="task-time">
            {{ formatTime(task.createdAt) }}
          </div>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.tasks-page {
  display: flex;
  justify-content: center;
  min-height: calc(100vh - 40px);
  padding: 2rem 1rem;
}

.tasks-container {
  width: 100%;
  max-width: 640px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.3rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 1.5rem;

  i { font-size: 1.2rem; }
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

.task-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.glass-card {
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
}

.task-card {
  padding: 14px 16px;
}

.task-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.task-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.task-label {
  font-size: 0.9rem;
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
  border-radius: 10px;

  &.badge-pending {
    background: rgba(251, 191, 36, 0.15);
    color: #fbbf24;
  }

  &.badge-processing {
    background: rgba(96, 165, 250, 0.15);
    color: #60a5fa;
  }

  &.badge-completed {
    background: rgba(52, 211, 153, 0.15);
    color: #34d399;
  }

  &.badge-failed {
    background: rgba(248, 113, 113, 0.15);
    color: #f87171;
  }

  &.badge-cancelled {
    background: rgba(156, 163, 175, 0.15);
    color: #9ca3af;
  }
}

.task-progress {
  margin-bottom: 4px;
}

.task-done {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: #34d399;
  margin-bottom: 4px;

  i { font-size: 0.85rem; }
}

.task-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;

  .error-info {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.8rem;
    color: #f87171;
    min-width: 0;

    i { flex-shrink: 0; font-size: 0.85rem; }
    span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  }
}

.task-cancelled {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: #9ca3af;
  margin-bottom: 4px;

  i { font-size: 0.85rem; }

  .remove-btn { margin-left: auto; }
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
  flex-shrink: 0;

  i { font-size: 0.85rem; }

  &:hover { color: #f87171; }
}

.task-time {
  font-size: 0.72rem;
  color: var(--text-muted);
  opacity: 0.7;
}

// Transition
.task-list-enter-active {
  transition: all 0.3s ease;
}

.task-list-leave-active {
  transition: all 0.2s ease;
}

.task-list-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.task-list-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.task-list-move {
  transition: transform 0.25s ease;
}
</style>
