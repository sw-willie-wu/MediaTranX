<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import { useResultsStore } from '@/stores/results'
import { useConfirm } from '@/composables/useConfirm'

const { t } = useI18n()
const resultsStore = useResultsStore()
const router = useRouter()
const route = useRoute()
const { confirm: showConfirm } = useConfirm()
const emit = defineEmits<{ (e: 'request-close'): void }>()

const count = computed(() => resultsStore.selectedIds.size)
const cat = computed(() => resultsStore.selectedCategory)
const canOpenInTool = computed(() => cat.value !== 'mixed' && cat.value !== null)

const targetToolLabel = computed(() => {
  if (!canOpenInTool.value) return ''
  return t(`nav.${cat.value}`)
})

async function doBatchSave() {
  const ids = [...resultsStore.selectedIds]
  await resultsStore.saveBatch(ids)
  resultsStore.clearSelection()
}

async function doBatchDelete() {
  const ok = await showConfirm({
    message: t('results.confirm_batch_delete', { count: count.value }),
    type: 'danger',
    confirmLabel: t('results.batch_delete'),
  })
  if (!ok) return
  const ids = [...resultsStore.selectedIds]
  await resultsStore.deleteBatch(ids)
  resultsStore.clearSelection()
}

async function doBatchOpen() {
  if (!canOpenInTool.value) return
  emit('request-close') // 先關抽屜給即時體感回饋，再切頁
  const ids = [...resultsStore.selectedIds]
  await resultsStore.openManyInTool(ids, router, route.path)
  resultsStore.clearSelection()
}
</script>

<template>
  <div v-if="count > 0" class="batch-bar">
    <span class="count">{{ t('common.selected_count', { count }) }}</span>
    <div class="actions">
      <button class="bb-btn" @click="doBatchSave">
        <i class="bi bi-download"></i>
        {{ t('results.batch_save') }}
      </button>
      <button
        class="bb-btn"
        :disabled="!canOpenInTool"
        :title="!canOpenInTool ? t('results.mixed_types_disabled') : ''"
        @click="doBatchOpen"
      >
        <i class="bi bi-box-arrow-up-right"></i>
        {{ canOpenInTool
          ? t('results.batch_open', { tool: targetToolLabel })
          : t('results.batch_open_disabled') }}
      </button>
      <button class="bb-btn danger" @click="doBatchDelete">
        <i class="bi bi-trash"></i>
        {{ t('results.batch_delete') }}
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.batch-bar {
  padding: 0.6rem 0.75rem;
  border-top: 1px solid var(--panel-border);
  background: var(--panel-bg-hover);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.count {
  font-size: 0.8rem;
  color: var(--text-primary);
  font-weight: 500;
}
.actions {
  flex: 1;
  display: flex;
  gap: 0.3rem;
  justify-content: flex-end;
  flex-wrap: wrap;
}
.bb-btn {
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--panel-border);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s ease;

  &:hover:not(:disabled) {
    background: var(--panel-bg-active);
    color: var(--text-primary);
  }
  &:disabled { opacity: 0.4; cursor: not-allowed; }

  i { margin-right: 3px; }

  &.danger:hover:not(:disabled) {
    background: color-mix(in srgb, var(--color-danger) 15%, transparent);
    color: var(--color-danger);
  }
}
</style>
