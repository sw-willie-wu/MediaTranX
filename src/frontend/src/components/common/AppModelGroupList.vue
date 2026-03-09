<script setup lang="ts">
import { ref, computed } from 'vue'

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
  downloadProgress: Record<string, number>
}>()

const emit = defineEmits<{
  download: [id: string]
  remove: [id: string]
}>()

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
    const first = variants[0]
    let familyLabel = first.label

    if (familyLabel.includes(' - ')) {
      familyLabel = familyLabel.split(' - ')[0]
    } else {
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

// 展開狀態（多 variant 的家族預設收合）
const expandedGroups = ref<Set<string>>(new Set())

function toggleGroup(family: string) {
  if (expandedGroups.value.has(family)) {
    expandedGroups.value.delete(family)
  } else {
    expandedGroups.value.add(family)
  }
}

function formatSize(mb: number): string {
  if (mb >= 1000) return `${(mb / 1000).toFixed(1)} GB`
  return `${mb} MB`
}
</script>

<template>
  <div class="model-group-list">
    <div v-for="group in groups" :key="group.family" class="model-group">

      <!-- 單一 variant：直接顯示為一行，不顯示 group-header -->
      <template v-if="group.variants.length === 1">
        <div class="model-item">
          <div class="model-info">
            <span class="model-label">{{ group.familyLabel }}</span>
            <span v-if="group.description" class="model-desc">{{ group.description }}</span>
          </div>
          <span class="model-size">{{ formatSize(group.variants[0].size_mb) }}</span>
          <div class="model-action">
            <template v-if="downloadingTaskId[group.variants[0].id]">
              <div class="download-progress">
                <div
                  class="progress-bar"
                  :style="{ width: `${((downloadProgress[group.variants[0].id] ?? 0) * 100).toFixed(0)}%` }"
                ></div>
              </div>
              <span class="progress-label">
                {{ ((downloadProgress[group.variants[0].id] ?? 0) * 100).toFixed(0) }}%
              </span>
            </template>
            <template v-else-if="group.variants[0].downloaded">
              <span class="status-badge installed">
                <i class="bi bi-check-circle-fill"></i> 已安裝
              </span>
              <button class="remove-btn" title="移除模型" @click="emit('remove', group.variants[0].id)">
                <i class="bi bi-trash3"></i>
              </button>
            </template>
            <button v-else class="download-btn" @click="emit('download', group.variants[0].id)">
              <i class="bi bi-download"></i> 安裝
            </button>
          </div>
        </div>
      </template>

      <!-- 多 variant：可折疊的 group-header + 子列表 -->
      <template v-else>
        <div class="group-header" @click="toggleGroup(group.family)">
          <i class="bi toggle-icon" :class="expandedGroups.has(group.family) ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
          <div class="group-info">
            <span class="group-label">{{ group.familyLabel }}</span>
            <span v-if="group.description" class="group-desc">{{ group.description }}</span>
          </div>
          <span class="group-count">{{ group.variants.length }} 個版本</span>
        </div>

        <Transition name="expand">
          <div v-show="expandedGroups.has(group.family)" class="variants-container">
            <div
              v-for="item in group.variants"
              :key="item.id"
              class="model-item variant-item"
            >
              <div class="model-info">
                <span class="model-label">{{ item.label }}</span>
              </div>
              <span class="model-size">{{ formatSize(item.size_mb) }}</span>
              <div class="model-action">
                <template v-if="downloadingTaskId[item.id]">
                  <div class="download-progress">
                    <div
                      class="progress-bar"
                      :style="{ width: `${((downloadProgress[item.id] ?? 0) * 100).toFixed(0)}%` }"
                    ></div>
                  </div>
                  <span class="progress-label">
                    {{ ((downloadProgress[item.id] ?? 0) * 100).toFixed(0) }}%
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
          </div>
        </Transition>
      </template>

    </div>
  </div>
</template>

<style scoped lang="scss">
.model-group-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.model-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

// ── Group header（多 variant 才顯示）──────────────────────────
.group-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.875rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
  }
}

.toggle-icon {
  font-size: 0.75rem;
  color: var(--text-muted);
  flex-shrink: 0;
  width: 12px;
}

.group-info {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  flex: 1;
  min-width: 0;
}

.group-label {
  color: var(--text-primary);
  font-size: 0.875rem;
  font-weight: 600;
}

.group-desc {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.group-count {
  color: var(--text-muted);
  font-size: 0.75rem;
  flex-shrink: 0;
}

// ── Variants container ────────────────────────────────────────
.variants-container {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding-left: 0.75rem;
  border-left: 2px solid var(--input-border);
  margin-left: 0.5rem;
}

// ── Model item（單 variant 和多 variant 共用）─────────────────
.model-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0.875rem;
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
  min-width: 52px;
  text-align: right;
}

.model-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  flex-shrink: 0;
  min-width: 100px;
  height: 2rem;
}

// ── Progress ──────────────────────────────────────────────────
.download-progress {
  background: var(--panel-border);
  border-radius: 4px;
  overflow: hidden;
  height: 4px;
  flex: 1;
  min-width: 60px;
}

.progress-bar {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.progress-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  min-width: 32px;
  text-align: right;
}

// ── Badges & Buttons ──────────────────────────────────────────
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
  padding: 0.35rem 0.7rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.15s ease;
}

.download-btn {
  background: var(--color-primary);
  color: white;

  &:hover {
    opacity: 0.85;
  }
}

.remove-btn {
  background: transparent;
  color: var(--text-muted);
  padding: 0.35rem;
  border: 1px solid var(--input-border);

  &:hover {
    color: #f87171;
    border-color: rgba(248, 113, 113, 0.4);
    background: rgba(248, 113, 113, 0.08);
  }
}

// ── Expand transition ─────────────────────────────────────────
.expand-enter-active,
.expand-leave-active {
  transition: all 0.25s ease;
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
</style>
