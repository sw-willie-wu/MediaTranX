<script setup lang="ts">
import { computed } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import ProgressBar from './ProgressBar.vue'

const taskStore = useTaskStore()

const activeTasks = computed(() => taskStore.activeTasks)
const hasActiveTasks = computed(() => activeTasks.value.length > 0)

function getStatusIcon(status: string): string {
  switch (status) {
    case 'pending':
      return 'bi-hourglass-split'
    case 'processing':
      return 'bi-arrow-repeat spin'
    case 'completed':
      return 'bi-check-circle-fill text-success'
    case 'failed':
      return 'bi-x-circle-fill text-danger'
    case 'cancelled':
      return 'bi-slash-circle text-warning'
    default:
      return 'bi-question-circle'
  }
}

function getTaskTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    'video.transcode': '影片轉檔',
    'video.subtitle.add': '添加字幕',
    'video.subtitle.generate': '生成字幕',
    'image.upscale': '圖片放大',
    'image.background': '去背',
    'subtitle.translate': '字幕翻譯',
  }
  return labels[type] || type
}

async function handleCancel(taskId: string) {
  await taskStore.cancelTask(taskId)
}
</script>

<template>
  <div class="task-queue" v-if="hasActiveTasks">
    <div class="task-queue-header">
      <i class="bi bi-list-task"></i>
      <span>進行中的任務</span>
      <span class="task-count">{{ activeTasks.length }}</span>
    </div>

    <div class="task-list">
      <div
        v-for="task in activeTasks"
        :key="task.taskId"
        class="task-item"
      >
        <div class="task-header">
          <i :class="['bi', getStatusIcon(task.status)]"></i>
          <span class="task-type">{{ getTaskTypeLabel(task.taskType) }}</span>
          <button
            v-if="task.status === 'processing' || task.status === 'pending'"
            class="btn-cancel"
            @click="handleCancel(task.taskId)"
            title="取消任務"
          >
            <i class="bi bi-x"></i>
          </button>
        </div>

        <ProgressBar
          :progress="task.progress"
          :message="task.message || undefined"
          show-percentage
        />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.task-queue {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  padding: 12px;
  backdrop-filter: blur(10px);
}

.task-queue-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 0.875rem;
  color: rgba(255, 255, 255, 0.8);

  .bi {
    font-size: 1rem;
  }

  .task-count {
    background: rgba(255, 255, 255, 0.2);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
  }
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-item {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  padding: 10px;
}

.task-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;

  .bi {
    font-size: 0.875rem;
  }

  .task-type {
    flex: 1;
    font-size: 0.8125rem;
    color: rgba(255, 255, 255, 0.9);
  }
}

.btn-cancel {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.2s;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.8);
  }
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
