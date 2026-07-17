<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResultsStore } from '@/stores/results'
import { useToolLabel } from '@/composables/useToolLabel'
import { useConfirm } from '@/composables/useConfirm'
import AppToggle from './common/AppToggle.vue'
import ResultCard from './results/ResultCard.vue'
import ResultsEmpty from './results/ResultsEmpty.vue'
import ResultsBatchBar from './results/ResultsBatchBar.vue'

const emit = defineEmits<{ (e: 'close'): void }>()
const { t } = useI18n()
const resultsStore = useResultsStore()
const { toolLabel } = useToolLabel()
const { confirm: showConfirm } = useConfirm()

const groupByTool = computed<boolean>({
  get: () => resultsStore.groupMode === 'tool',
  set: (v) => { resultsStore.groupMode = v ? 'tool' : 'time' },
})

function onClickOutside(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest('.results-dropdown, .results-button-wrap')
  if (!el) emit('close')
}
function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

async function confirmClearAll() {
  const ok = await showConfirm({
    message: t('results.confirm_clear'),
    type: 'danger',
    confirmLabel: t('results.clear'),
  })
  if (!ok) return
  await resultsStore.clearAll()
}

onMounted(() => {
  document.addEventListener('mousedown', onClickOutside)
  document.addEventListener('keydown', onEsc)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onClickOutside)
  document.removeEventListener('keydown', onEsc)
})
</script>

<template>
  <div class="results-dropdown">
    <header class="dd-header">
      <label class="select-all" @click.stop>
        <input
          type="checkbox"
          :checked="resultsStore.allSelected"
          :indeterminate.prop="resultsStore.someSelected"
          :disabled="resultsStore.results.length === 0"
          @change="resultsStore.toggleSelectAll"
        />
        <span>{{ t('results.select_all') }}</span>
      </label>
      <span class="dd-count" v-if="resultsStore.results.length > 0">
        ({{ resultsStore.results.length }})
      </span>
      <div class="spacer"></div>
      <AppToggle v-model="groupByTool">{{ t('results.group_by_tool') }}</AppToggle>
      <button
        class="header-btn"
        :disabled="resultsStore.results.length === 0"
        @click="confirmClearAll"
      >
        {{ t('results.clear') }}
      </button>
    </header>
    <div class="dd-body">
      <ResultsEmpty v-if="resultsStore.results.length === 0" />
      <template v-else-if="resultsStore.groupMode === 'time'">
        <ResultCard
          v-for="r in resultsStore.sortedResults"
          :key="r.fileId"
          :entry="r"
          @request-close="emit('close')"
        />
      </template>
      <template v-else>
        <div v-for="[toolId, items] in resultsStore.groupedByTool" :key="toolId" class="group">
          <div class="group-header">
            {{ toolLabel(toolId) }}
            <span class="group-count">({{ items.length }})</span>
          </div>
          <ResultCard v-for="r in items" :key="r.fileId" :entry="r" @request-close="emit('close')" />
        </div>
      </template>
    </div>
    <ResultsBatchBar @request-close="emit('close')" />
  </div>
</template>

<style lang="scss" scoped>
.results-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  width: 420px;
  max-height: 50vh;
  display: flex;
  flex-direction: column;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  z-index: 1100;
  -webkit-app-region: no-drag;
}
.dd-header {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--panel-border);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.dd-count { font-size: 0.8rem; color: var(--text-muted); }
.dd-body { flex: 1; overflow-y: auto; }
.select-all {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}
.select-all input { cursor: pointer; }
.select-all input:disabled { cursor: not-allowed; opacity: 0.4; }
.spacer { flex: 1; }
:deep(.app-toggle-track) {
  width: 26px;
  height: 14px;
  border-radius: 7px;
}
:deep(.app-toggle-thumb) {
  top: 1px;
  left: 1px;
  width: 10px;
  height: 10px;
}
:deep(.app-toggle-track.is-on .app-toggle-thumb) {
  transform: translateX(12px);
}
:deep(.app-toggle-label) {
  font-size: 0.75rem;
  color: var(--text-secondary);
}
.header-btn {
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--panel-border);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s ease;

  &:hover:not(:disabled) { background: var(--panel-bg-hover); color: var(--text-primary); }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
}
.group-header {
  padding: 0.5rem 0.75rem;
  background: var(--panel-bg-hover);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-primary);
}
.group-count { color: var(--text-muted); font-weight: 400; margin-left: 0.3rem; }
</style>
