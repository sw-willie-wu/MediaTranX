<script setup lang="ts">
import { ref, computed } from 'vue'
import { useTaskStore } from '@/stores/tasks'

interface ModelListItem {
  id: string
  label: string
  description?: string
  ready: boolean
  size_mb: number
}

const props = defineProps<{
  items: ModelListItem[]
  downloadingTaskId: Record<string, string>
}>()

const emit = defineEmits<{
  download: [id: string]
  remove: [id: string]
}>()

const taskStore = useTaskStore()

const COLLAPSE_THRESHOLD = 4

const isCollapsible = computed(() => props.items.length > COLLAPSE_THRESHOLD)
const isCollapsed = ref(isCollapsible.value)

const visibleItems = computed(() =>
  isCollapsed.value ? props.items.slice(0, COLLAPSE_THRESHOLD) : props.items
)

function getTask(id: string) {
  const taskId = props.downloadingTaskId[id]
  if (!taskId) return undefined
  return taskStore.tasks.get(taskId)
}

function formatSize(mb: number): string {
  if (mb >= 1000) return `${(mb / 1000).toFixed(1)} GB`
  return `${mb} MB`
}
</script>

<template>
  <div class="model-list">
    <TransitionGroup name="list">
      <div v-for="item in visibleItems" :key="item.id" class="model-item">
        <div class="model-info">
          <span class="model-label">{{ item.label }}</span>
          <span v-if="item.description" class="model-desc">{{ item.description }}</span>
        </div>
        <span class="model-size">{{ formatSize(item.size_mb) }}</span>
        <div class="model-action">
          <template v-if="getTask(item.id)">
            <div class="download-progress">
              <div
                class="progress-bar"
                :style="{ width: `${(getTask(item.id)!.progress * 100).toFixed(0)}%` }"
              ></div>
            </div>
            <span class="progress-label">
              {{ (getTask(item.id)!.progress * 100).toFixed(0) }}%
            </span>
          </template>
          <template v-else-if="item.ready">
            <span class="status-badge installed">
              <i class="bi bi-check-circle-fill"></i> 已安裝
            </span>
            <button class="remove-btn" title="移除模型" @click="emit('remove', item.id)">
              <i class="bi bi-trash3"></i>
            </button>
          </template>
          <button v-else class="download-btn" @click="emit('download', item.id)">
            <i class="bi bi-download"></i> 安裝
          </button>
        </div>
      </div>
    </TransitionGroup>

    <button
      v-if="isCollapsible"
      class="collapse-toggle"
      @click="isCollapsed = !isCollapsed"
    >
      <template v-if="isCollapsed">
        顯示全部 {{ items.length }} 項 <i class="bi bi-chevron-down"></i>
      </template>
      <template v-else>
        收合 <i class="bi bi-chevron-up"></i>
      </template>
    </button>
  </div>
</template>

<style scoped lang="scss">
.model-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.model-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
}

.model-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.model-label {
  color: var(--text-primary);
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-desc {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.model-size {
  color: var(--text-muted);
  font-size: 0.8rem;
  white-space: nowrap;
  flex-shrink: 0;
}

.model-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  flex-shrink: 0;
  min-width: 130px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.6rem;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 500;

  &.installed {
    background: rgba(16, 185, 129, 0.12);
    color: #10b981;
  }
}

.download-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.75rem;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.22);
    color: var(--text-primary);
  }
}

.remove-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;

  &:hover {
    background: rgba(239, 68, 68, 0.1);
    border-color: rgba(239, 68, 68, 0.25);
    color: #ef4444;
  }
}

.download-progress {
  width: 80px;
  height: 6px;
  background: var(--panel-border);
  border-radius: 3px;
  overflow: hidden;

  .progress-bar {
    height: 100%;
    background: var(--color-primary);
    border-radius: 3px;
    transition: width 0.3s ease;
  }
}

.progress-label {
  color: var(--text-secondary);
  font-size: 0.75rem;
  min-width: 32px;
  text-align: right;
}

.collapse-toggle {
  align-self: flex-start;
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.25rem 0;
  transition: color 0.15s ease;

  i {
    margin-left: 0.25rem;
    font-size: 0.7rem;
  }

  &:hover {
    color: var(--text-secondary);
  }
}

/* 列表動畫 */
.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}

.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.list-move {
  transition: transform 0.3s ease;
}
</style>
