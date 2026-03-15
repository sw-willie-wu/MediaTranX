<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { apiFetch } from '@/composables/useApi'
import AppModelGroupList from '@/components/common/AppModelGroupList.vue'

const taskStore = useTaskStore()

interface ModelItem {
  id: string
  label: string
  category: string
  downloaded: boolean
  size_mb: number
  family: string
  variant: string
  description?: string
}

interface ModelsStatus {
  models: ModelItem[]
}

const modelStatus = ref<ModelsStatus | null>(null)
const modelStatusLoading = ref(false)
const downloadingTaskId = ref<Record<string, string>>({})

const downloadProgress = computed(() => {
  const result: Record<string, number> = {}
  for (const [id, taskId] of Object.entries(downloadingTaskId.value)) {
    result[id] = taskStore.tasks.get(taskId)?.progress ?? 0
  }
  return result
})

async function loadModelStatus() {
  modelStatusLoading.value = true
  try {
    const res = await apiFetch('/setup/models')
    if (res.ok) modelStatus.value = await res.json()
  } catch (e) {
    console.error('Failed to load model status', e)
  } finally {
    modelStatusLoading.value = false
  }
}

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
    message: `下載 ${id}`,
    result: null,
    error: null,
    label: `下載 ${id}`,
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
  if (res.ok && modelStatus.value) {
    const model = modelStatus.value.models.find(m => m.id === id)
    if (model) model.downloaded = false
  }
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
        delete downloadProgress.value[itemId]
        if (task.status === 'completed' && modelStatus.value) {
          const model = modelStatus.value.models.find(m => m.id === itemId)
          if (model) model.downloaded = true
        }
      }
    }
  },
)

onMounted(loadModelStatus)
</script>

<template>
  <h6 class="section-title mt">模型與工具</h6>
  <p class="download-hint"><i class="bi bi-info-circle"></i> 最多同時進行 4 個下載，超過將自動排隊</p>

  <div v-if="modelStatusLoading" class="models-loading">
    <div class="spinner"></div>
    <span>載入中...</span>
  </div>

  <template v-else-if="modelStatus">
    <label class="section-subtitle">超解析工具</label>
    <AppModelGroupList
      :items="modelStatus.models.filter(m => m.category === 'upscale')"
      :downloadingTaskId="downloadingTaskId"
      :downloadProgress="downloadProgress"
      @download="downloadItem"
      @remove="removeItem"
    />

    <label class="section-subtitle">人臉修復</label>
    <AppModelGroupList
      :items="modelStatus.models.filter(m => m.category === 'face_restore')"
      :downloadingTaskId="downloadingTaskId"
      :downloadProgress="downloadProgress"
      @download="downloadItem"
      @remove="removeItem"
    />

    <label class="section-subtitle">語音識別</label>
    <AppModelGroupList
      :items="modelStatus.models.filter(m => m.category === 'stt')"
      :downloadingTaskId="downloadingTaskId"
      :downloadProgress="downloadProgress"
      @download="downloadItem"
      @remove="removeItem"
    />

    <label class="section-subtitle">翻譯模型</label>
    <AppModelGroupList
      :items="modelStatus.models.filter(m => m.category === 'translate')"
      :downloadingTaskId="downloadingTaskId"
      :downloadProgress="downloadProgress"
      @download="downloadItem"
      @remove="removeItem"
    />

    <label class="section-subtitle">VLM OCR 模型</label>
    <AppModelGroupList
      :items="modelStatus.models.filter(m => m.category === 'vlm')"
      :downloadingTaskId="downloadingTaskId"
      :downloadProgress="downloadProgress"
      @download="downloadItem"
      @remove="removeItem"
    />

    <label class="section-subtitle">圖像分割</label>
    <AppModelGroupList
      :items="modelStatus.models.filter(m => m.category === 'segment')"
      :downloadingTaskId="downloadingTaskId"
      :downloadProgress="downloadProgress"
      @download="downloadItem"
      @remove="removeItem"
    />

    <button class="btn-secondary refresh-btn" @click="loadModelStatus">
      <i class="bi bi-arrow-clockwise"></i> 重新整理
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
</style>
