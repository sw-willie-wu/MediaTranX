<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import type { ResultEntry } from '@/stores/results'
import { useResultsStore } from '@/stores/results'
import { useToolLabel } from '@/composables/useToolLabel'
import { detectMediaType } from '@/utils/mediaType'

const { t } = useI18n()
const { toolLabel: resolveToolLabel } = useToolLabel()
const resultsStore = useResultsStore()
const router = useRouter()
const route = useRoute()
const props = defineProps<{ entry: ResultEntry }>()
const emit = defineEmits<{ (e: 'request-close'): void }>()

const isSelected = computed(() => resultsStore.selectedIds.has(props.entry.fileId))

const targetType = computed(() =>
  detectMediaType(new File([], props.entry.filename, { type: props.entry.mimeType })),
)
const canOpenInTool = computed(() => targetType.value !== null)
const targetToolLabel = computed(() =>
  targetType.value ? t(`nav.${targetType.value}`) : '',
)

const sizeStr = computed(() => {
  const b = props.entry.fileSize
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
})

const toolLabel = computed(() => resolveToolLabel(props.entry.toolId))

const sourceLabel = computed(() =>
  props.entry.originalFilename
    ? t('results.from_source', { name: props.entry.originalFilename })
    : ''
)

const icon = computed(() => {
  const e = props.entry.filename.toLowerCase()
  if (/\.(jpg|jpeg|png|apng|gif|webp|bmp|svg|avif|tiff|heic|heif|ico)$/.test(e)) return 'bi-image'
  if (/\.(mp3|wav|flac|ogg|aac|m4a|opus|mid|midi)$/.test(e)) return 'bi-music-note-beamed'
  if (/\.(mp4|mov|webm|avi|mkv|flv|wmv|m4v)$/.test(e)) return 'bi-camera-video'
  return 'bi-file-earmark-text'
})

const isSaved = computed(() => !!props.entry.savedPath)
const isSaving = computed(() => resultsStore.savingIds.has(props.entry.fileId))

function onToggle() { resultsStore.toggleSelect(props.entry.fileId) }
function onPreview() { resultsStore.previewOne(props.entry.fileId) }
function onSave() { resultsStore.saveOne(props.entry.fileId) }
function onBrowse() { resultsStore.browseSaved(props.entry.fileId) }
function onRemove() { resultsStore.removeOne(props.entry.fileId) }
function onOpenInTool() {
  emit('request-close') // 先關抽屜給即時體感回饋，再切頁（不 await、不阻擋 push）
  resultsStore.openInTool(props.entry.fileId, router, route.path)
}
</script>

<template>
  <div class="result-card" :class="{ selected: isSelected }">
    <label class="card-check" @click.stop>
      <input type="checkbox" :checked="isSelected" @change="onToggle" />
    </label>
    <i :class="['bi', icon, 'card-icon']"></i>
    <div class="card-body">
      <div class="card-name" :title="entry.filename">{{ entry.filename }}</div>
      <div class="card-meta">
        <span>{{ sizeStr }}</span>
        <span> · </span>
        <span>{{ toolLabel }}</span>
        <span v-if="sourceLabel"> · {{ sourceLabel }}</span>
      </div>
      <div class="card-actions">
        <button class="act-btn" @click="onPreview">
          <i class="bi bi-eye"></i>
          {{ t('results.preview') }}
        </button>
        <button v-if="canOpenInTool" class="act-btn" @click="onOpenInTool">
          <i class="bi bi-box-arrow-up-right"></i>
          {{ t('results.add_to_tool', { tool: targetToolLabel }) }}
        </button>
        <button v-if="isSaving" class="act-btn" disabled>
          <span class="spinner"></span>
          {{ t('results.saving') }}
        </button>
        <button v-else-if="isSaved" class="act-btn" @click="onBrowse">
          <i class="bi bi-folder2-open"></i>
          {{ t('results.browse_saved') }}
        </button>
        <button v-else class="act-btn" @click="onSave">
          <i class="bi bi-download"></i>
          {{ t('results.save_as') }}
        </button>
      </div>
    </div>
    <button class="card-remove" :title="t('results.remove')" @click="onRemove">
      <i class="bi bi-x"></i>
    </button>
  </div>
</template>

<style lang="scss" scoped>
.result-card {
  display: flex;
  align-items: flex-start;
  gap: 0.7rem;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--panel-border);
  transition: background 0.15s ease;

  &:last-child { border-bottom: none; }
  &:hover { background: var(--panel-bg-hover); }
}
.result-card.selected { background: var(--panel-bg-active); }
.result-card.selected:hover { background: var(--panel-bg-active); }
.card-check {
  display: flex;
  align-items: center;
  align-self: center;
  cursor: pointer;
}
.card-check input { cursor: pointer; }
.card-icon {
  font-size: 1.1rem;
  color: var(--text-secondary);
  align-self: center;
}
.card-body { flex: 1; min-width: 0; }
.card-name {
  font-size: 0.85rem;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-meta {
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-top: 2px;
}
.card-actions {
  display: flex;
  gap: 0.35rem;
  margin-top: 0.4rem;
}
.act-btn {
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  gap: 3px;

  &:hover:not(:disabled) { background: var(--panel-bg-hover); color: var(--text-primary); }
  &:disabled { cursor: default; opacity: 0.7; }

  i { margin-right: 0; }
}
.spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid var(--text-muted);
  border-top-color: var(--text-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.card-remove {
  align-self: flex-start;
  width: 22px;
  height: 22px;
  padding: 0;
  background: transparent;
  border: 0;
  color: var(--text-muted);
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;

  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
}
</style>
