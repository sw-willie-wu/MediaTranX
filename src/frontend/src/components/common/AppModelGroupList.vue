<script setup lang="ts">
import { ref, computed } from 'vue'
import { useTaskStore } from '@/stores/tasks'

interface ModelItem {
  id: string
  family: string
  variant: string
  label: string
  description?: string
  downloaded: boolean
  size_mb: number
}

interface ModelGroup {
  family: string
  familyLabel: string
  description: string
  variants: ModelItem[]
}

const props = defineProps<{
  items: ModelItem[]
  downloadingTaskId: Record<string, string>
}>()

const emit = defineEmits<{
  download: [id: string]
  remove: [id: string]
}>()

const taskStore = useTaskStore()

// 按 family 分組
const groups = computed<ModelGroup[]>(() => {
  const familyMap = new Map<string, ModelItem[]>()
  
  props.items.forEach(item => {
    if (!familyMap.has(item.family)) {
      familyMap.set(item.family, [])
    }
    familyMap.get(item.family)!.push(item)
  })
  
  return Array.from(familyMap.entries()).map(([family, variants]) => {
    // 從第一個 variant 獲取家族信息
    const first = variants[0]
    // 提取家族名稱（去掉尺寸和量化信息）
    let familyLabel = first.label
    
    // 如果有 ' - '，取前面部分（PTH 模型）
    if (familyLabel.includes(' - ')) {
      familyLabel = familyLabel.split(' - ')[0]
    } else {
      // 去掉尺寸（如 TINY, 4B, 1.7B 等）和量化信息（如 Q4_K_M）
      familyLabel = familyLabel
        .replace(/\s+(TINY|BASE|SMALL|MEDIUM|LARGE-V3|\d+\.?\d*B)\s+Q[0-9A-Z_]+$/i, '')
        .replace(/\s+(TINY|BASE|SMALL|MEDIUM|LARGE-V3|\d+\.?\d*B)$/i, '')
    }
    
    return {
      family,
      familyLabel,
      description: first.description || '',
      variants: variants.sort((a, b) => a.label.localeCompare(b.label))
    }
  })
})

// 展開狀態
const expandedGroups = ref<Set<string>>(new Set())

// 默認全部展開單變體的家族
groups.value.forEach(group => {
  if (group.variants.length === 1) {
    expandedGroups.value.add(group.family)
  }
})

function toggleGroup(family: string) {
  if (expandedGroups.value.has(family)) {
    expandedGroups.value.delete(family)
  } else {
    expandedGroups.value.add(family)
  }
}

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
  <div class="model-group-list">
    <div v-for="group in groups" :key="group.family" class="model-group">
      <!-- 家族標題 -->
      <div 
        class="group-header"
        :class="{ 'single-variant': group.variants.length === 1 }"
        @click="group.variants.length > 1 && toggleGroup(group.family)"
      >
        <div class="group-info">
          <i 
            v-if="group.variants.length > 1"
            class="bi" 
            :class="expandedGroups.has(group.family) ? 'bi-chevron-down' : 'bi-chevron-right'"
          ></i>
          <span class="group-label">{{ group.familyLabel }}</span>
          <span class="group-count" v-if="group.variants.length > 1">
            ({{ group.variants.length }} 個變體)
          </span>
        </div>
        <span class="group-desc">{{ group.description }}</span>
      </div>

      <!-- 變體列表 -->
      <Transition name="expand">
        <div 
          v-show="expandedGroups.has(group.family) || group.variants.length === 1" 
          class="variants-container"
        >
          <TransitionGroup name="list">
            <div 
              v-for="item in group.variants" 
              :key="item.id" 
              class="model-item"
            >
              <div class="model-info">
                <span class="model-label">{{ item.label }}</span>
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
                <template v-else-if="item.downloaded">
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
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped lang="scss">
.model-group-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1rem;
}

.model-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  
  &:not(.single-variant):hover {
    background: var(--surface-hover);
  }
  
  &.single-variant {
    cursor: default;
  }
}

.group-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
}

.group-label {
  color: var(--text-primary);
  font-size: 0.95rem;
  font-weight: 600;
}

.group-count {
  color: var(--text-muted);
  font-size: 0.8rem;
}

.group-desc {
  color: var(--text-muted);
  font-size: 0.8rem;
}

.variants-container {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-left: 1.5rem;
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

.download-progress {
  background: var(--input-bg);
  border-radius: 4px;
  overflow: hidden;
  height: 4px;
  flex: 1;
}

.progress-bar {
  height: 100%;
  background: var(--primary);
  transition: width 0.3s ease;
}

.progress-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  min-width: 40px;
  text-align: right;
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
  
  i { font-size: 0.72rem; }
}

.download-btn,
.remove-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.4rem 0.75rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.2s ease;
}

.download-btn {
  background: var(--primary);
  color: white;
  
  &:hover {
    background: var(--primary-hover);
  }
}

.remove-btn {
  background: transparent;
  color: var(--danger);
  padding: 0.4rem;
  
  &:hover {
    background: var(--danger-bg);
  }
}

/* Expand transition */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
}

.expand-enter-to,
.expand-leave-from {
  max-height: 2000px;
  opacity: 1;
}

/* List transition */
.list-move,
.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}

.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}

.list-leave-active {
  position: absolute;
}
</style>
