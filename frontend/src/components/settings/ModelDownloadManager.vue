<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/tasks'
import { useModelStore } from '@/stores/models'
import { apiFetch } from '@/composables/useApi'
import AppModelGroupList from '@/components/common/AppModelGroupList.vue'

const { t } = useI18n()

const taskStore = useTaskStore()
const modelStore = useModelStore()

const activeTab = ref('')
const downloadingTaskId = ref<Record<string, string>>({})

const downloadProgress = computed(() => {
  const result: Record<string, number> = {}
  for (const [id, taskId] of Object.entries(downloadingTaskId.value)) {
    result[id] = taskStore.tasks.get(taskId)?.progress ?? 0
  }
  return result
})

// 初始化：載入模型後選中第一個 tab
watch(() => modelStore.categories, (cats) => {
  if (cats.length && !activeTab.value) {
    activeTab.value = cats[0].key
  }
}, { immediate: true })

async function downloadItem(id: string) {
  const res = await apiFetch('/setup/models/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (!res.ok) { console.error('Download request failed:', res.statusText); return }
  const { task_id } = await res.json()
  downloadingTaskId.value[id] = task_id

  taskStore.addTask({
    taskId: task_id,
    taskType: 'setup.download',
    status: 'pending',
    progress: 0,
    message: `${t('settings.models.title')} ${id}`,
    result: null,
    error: null,
    label: `${t('settings.models.title')} ${id}`,
    createdAt: new Date(),
    updatedAt: new Date(),
  })
}

async function removeItem(id: string) {
  const res = await apiFetch('/setup/models/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (res.ok) modelStore.setDownloaded(id, false)
}

watch(
  () => Object.entries(downloadingTaskId.value).map(([, taskId]) =>
    taskStore.tasks.get(taskId)?.status
  ),
  () => {
    for (const [itemId, taskId] of Object.entries(downloadingTaskId.value)) {
      const task = taskStore.tasks.get(taskId)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        delete downloadingTaskId.value[itemId]
        if (task.status === 'completed') modelStore.setDownloaded(itemId, true)
      }
    }
  },
)

onMounted(() => modelStore.fetchModels())
</script>

<template>
  <h6 class="section-title mt">{{ $t('settings.models.title') }}</h6>
  <p class="download-hint"><i class="bi bi-info-circle"></i> {{ $t('settings.models.hint') }}</p>

  <div v-if="modelStore.loading && !modelStore.loaded" class="models-loading">
    <div class="spinner"></div>
    <span>{{ $t('settings.models.loading') }}</span>
  </div>

  <template v-else-if="modelStore.loaded">
    <!-- Category tabs -->
    <div class="category-tabs">
      <button
        v-for="cat in modelStore.categories"
        :key="cat.key"
        class="category-tab"
        :class="{ 'is-active': activeTab === cat.key }"
        @click="activeTab = cat.key"
      >{{ $t(`settings.models.category_${cat.key}`) }}</button>
    </div>

    <!-- Active tab content -->
    <AppModelGroupList
      :items="modelStore.byCategory(activeTab)"
      :downloadingTaskId="downloadingTaskId"
      :downloadProgress="downloadProgress"
      @download="downloadItem"
      @remove="removeItem"
    />

    <button class="btn-secondary refresh-btn" @click="modelStore.fetchModels()">
      <i class="bi bi-arrow-clockwise"></i> {{ $t('settings.models.refresh') }}
    </button>
  </template>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.models-loading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.refresh-btn { margin-top: 1rem; }

.download-hint {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

// ── Category tabs ─────────────────────────────────────────────
.category-tabs {
  display: flex;
  gap: 0.25rem;
  margin-bottom: 1rem;
  padding: 0.25rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
}

.category-tab {
  flex: 1;
  padding: 0.4rem 0.5rem;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover:not(.is-active) {
    color: var(--text-secondary);
    background: var(--panel-bg-hover);
  }

  &.is-active {
    background: var(--color-primary);
    color: white;
    font-weight: 500;
  }
}
</style>
