<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t, te } = useI18n()

interface ModelItem {
  id: string
  family: string
  variant: string
  label: string
  description?: string
  capabilities?: string[]
  downloaded: boolean
  size_mb: number
  vram_mb?: number
}

interface FamilyGroup {
  family: string
  familyLabel: string
  description: string
  capabilities: string[]
  items: ModelItem[]
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

const groups = computed<FamilyGroup[]>(() => {
  const familyMap = new Map<string, ModelItem[]>()

  props.items.forEach(item => {
    if (!familyMap.has(item.family)) {
      familyMap.set(item.family, [])
    }
    familyMap.get(item.family)!.push(item)
  })

  return Array.from(familyMap.entries()).map(([family, items]) => {
    const first = items[0]
    let familyLabel = first.label

    // 從 label 中提取 family 名稱（去除 variant 部分）
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
      capabilities: first.capabilities || [],
      items: items.sort((a, b) => a.size_mb - b.size_mb),
    }
  })
})

/** 從完整 label 提取 variant 部分（去掉 family 前綴） */
function variantLabel(item: ModelItem, group: FamilyGroup): string {
  const label = item.label
  if (label.includes(' - ')) return label.split(' - ').slice(1).join(' - ')
  // GGUF/VLM: "TranslateGemma 4B Q4_K_M" → "4B Q4_K_M"
  const prefix = group.familyLabel
  if (label.startsWith(prefix)) {
    const rest = label.slice(prefix.length).trim()
    return rest || label
  }
  return label
}

function formatSize(mb: number): string {
  if (mb >= 1000) return `${(mb / 1000).toFixed(1)} GB`
  return `${mb} MB`
}

/** Translate a description that may be an i18n key or a composite "key1||key2" */
function tDesc(desc: string): string {
  if (!desc) return ''
  if (desc.includes('||')) {
    return desc.split('||').map(part => te(part) ? t(part) : part).join(' · ')
  }
  return te(desc) ? t(desc) : desc
}
</script>

<template>
  <div class="model-group-list">
    <div v-for="group in groups" :key="group.family" class="family-card">
      <!-- Family header -->
      <div class="family-header">
        <span class="family-label">{{ group.familyLabel }}</span>
        <div v-if="group.capabilities.length" class="family-caps">
          <span v-for="cap in group.capabilities" :key="cap" class="cap-badge" :class="`cap-${cap}`">{{ cap }}</span>
        </div>
        <span v-if="group.description" class="family-desc">{{ tDesc(group.description) }}</span>
      </div>

      <!-- Single variant: action in header row -->
      <template v-if="group.items.length === 1">
        <div class="model-row">
          <span class="row-label">{{ group.items[0].variant === 'default' ? group.familyLabel : variantLabel(group.items[0], group) }}</span>
          <span class="row-size">{{ formatSize(group.items[0].size_mb) }}</span>
          <span v-if="group.items[0].vram_mb" class="row-vram">{{ formatSize(group.items[0].vram_mb) }} VRAM</span>
          <span v-else class="row-vram"></span>
          <div class="row-action">
            <template v-if="downloadingTaskId[group.items[0].id]">
              <template v-if="(downloadProgress[group.items[0].id] ?? 0) === 0">
                <span class="status-queued">{{ $t('tasks.active.pending') }}...</span>
              </template>
              <template v-else>
                <div class="download-progress">
                  <div class="progress-bar" :style="{ width: `${((downloadProgress[group.items[0].id] ?? 0) * 100).toFixed(0)}%` }"></div>
                </div>
                <span class="progress-label">{{ ((downloadProgress[group.items[0].id] ?? 0) * 100).toFixed(0) }}%</span>
              </template>
            </template>
            <template v-else-if="group.items[0].downloaded">
              <span class="status-installed"><i class="bi bi-check-circle-fill"></i> {{ $t('settings.ai.installed') }}</span>
              <button class="remove-btn" :title="$t('settings.models.remove_model')" @click="emit('remove', group.items[0].id)"><i class="bi bi-trash3"></i></button>
            </template>
            <button v-else class="download-btn" @click="emit('download', group.items[0].id)"><i class="bi bi-download"></i> {{ $t('settings.models.install') }}</button>
          </div>
        </div>
      </template>

      <!-- Multiple variants: list rows -->
      <template v-else>
        <div
          v-for="item in group.items"
          :key="item.id"
          class="model-row"
        >
          <span class="row-label">{{ variantLabel(item, group) }}</span>
          <span class="row-size">{{ formatSize(item.size_mb) }}</span>
          <span v-if="item.vram_mb" class="row-vram">{{ formatSize(item.vram_mb) }} VRAM</span>
          <span v-else class="row-vram"></span>
          <div class="row-action">
            <template v-if="downloadingTaskId[item.id]">
              <template v-if="(downloadProgress[item.id] ?? 0) === 0">
                <span class="status-queued">{{ $t('tasks.active.pending') }}...</span>
              </template>
              <template v-else>
                <div class="download-progress">
                  <div class="progress-bar" :style="{ width: `${((downloadProgress[item.id] ?? 0) * 100).toFixed(0)}%` }"></div>
                </div>
                <span class="progress-label">{{ ((downloadProgress[item.id] ?? 0) * 100).toFixed(0) }}%</span>
              </template>
            </template>
            <template v-else-if="item.downloaded">
              <span class="status-installed"><i class="bi bi-check-circle-fill"></i> {{ $t('settings.ai.installed') }}</span>
              <button class="remove-btn" :title="$t('settings.models.remove_model')" @click="emit('remove', item.id)"><i class="bi bi-trash3"></i></button>
            </template>
            <button v-else class="download-btn" @click="emit('download', item.id)"><i class="bi bi-download"></i> {{ $t('settings.models.install') }}</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
.model-group-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

// ── Family card ───────────────────────────────────────────────
.family-card {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 12px;
  overflow: hidden;
}

.family-header {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.6rem 0.875rem 0.25rem;
}

.family-label {
  color: var(--text-primary);
  font-size: 0.85rem;
  font-weight: 600;
}

.family-caps {
  display: flex;
  gap: 0.25rem;
}

.cap-badge {
  font-size: 0.65rem;
  padding: 0.1rem 0.4rem;
  border-radius: 50rem;
  font-weight: 600;

  &.cap-text {
    color: var(--color-info);
    background: color-mix(in srgb, var(--color-info) 20%, transparent);
  }
  &.cap-vision {
    color: var(--color-success);
    background: color-mix(in srgb, var(--color-success) 20%, transparent);
  }
}

.family-desc {
  color: var(--text-muted);
  font-size: 0.75rem;
}

// ── Model row（統一四欄排版）──────────────────────────────────
.model-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.875rem;
  transition: background 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
  }

  &:last-child {
    padding-bottom: 0.6rem;
  }
}

.row-label {
  flex: 1;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 0.8rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-size {
  flex-shrink: 0;
  min-width: 56px;
  text-align: right;
  color: var(--text-muted);
  font-size: 0.78rem;
}

.row-vram {
  flex-shrink: 0;
  min-width: 80px;
  text-align: right;
  color: var(--text-muted);
  font-size: 0.72rem;
  opacity: 0.7;
}

// ── Action column ─────────────────────────────────────────────
.row-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.4rem;
  flex-shrink: 0;
  min-width: 90px;
  height: 1.75rem;
}

// ── Progress ──────────────────────────────────────────────────
.download-progress {
  background: var(--panel-border);
  border-radius: 4px;
  overflow: hidden;
  height: 4px;
  flex: 1;
  min-width: 50px;
}

.progress-bar {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.progress-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  min-width: 28px;
  text-align: right;
}

// ── Status & Buttons ──────────────────────────────────────────
.status-queued {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-style: italic;
}

.status-installed {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-success);

  i { font-size: 0.68rem; }
}

.download-btn,
.remove-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  padding: 0.25rem 0.6rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.75rem;
  font-family: inherit;
  transition: all 0.15s ease;
}

.download-btn {
  background: var(--color-primary);
  color: white;

  &:hover { opacity: 0.85; }
}

.remove-btn {
  background: transparent;
  color: var(--text-muted);
  padding: 0.25rem;
  border: 1px solid var(--input-border);

  &:hover {
    color: var(--color-danger);
    border-color: color-mix(in srgb, var(--color-danger) 40%, transparent);
    background: color-mix(in srgb, var(--color-danger) 8%, transparent);
  }
}
</style>
