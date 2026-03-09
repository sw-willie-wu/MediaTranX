<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { apiFetch } from '@/composables/useApi'
import AppModelGroupList from '@/components/common/AppModelGroupList.vue'

const taskStore = useTaskStore()

// ── AI 推理環境 ────────────────────────────────────────────────

const aiEnvLoading = ref(true)
const aiEnvReady = ref(false)
const llamaReady = ref(false)
const aiTorchIndex = ref('cpu')
const aiDriverVersion = ref<string | null>(null)
const aiInstallTaskId = ref<string | null>(null)
const aiInstalling = ref(false)
const aiInstalled = ref(false)

const aiInstallTask = computed(() => {
  if (!aiInstallTaskId.value) return null
  return taskStore.tasks.get(aiInstallTaskId.value) ?? null
})

const AI_CACHE_KEY = 'ai-module-cache'

function readAiCache() {
  try {
    const s = localStorage.getItem(AI_CACHE_KEY)
    return s ? JSON.parse(s) : null
  } catch { return null }
}

function writeAiCache(data: { aiEnvReady: boolean; llamaReady: boolean; torchIndex: string; driverVersion: string | null }) {
  localStorage.setItem(AI_CACHE_KEY, JSON.stringify(data))
}

async function loadAiEnvStatus() {
  const cache = readAiCache()
  if (cache) {
    aiEnvReady.value = cache.aiEnvReady
    llamaReady.value = cache.llamaReady
    aiTorchIndex.value = cache.torchIndex ?? 'cpu'
    aiDriverVersion.value = cache.driverVersion ?? null
    aiEnvLoading.value = false
  }

  try {
    const res = await apiFetch('/setup/status')
    if (!res.ok) return
    const data = await res.json()
    aiEnvReady.value = data.ai_env_ready
    llamaReady.value = data.llama_ready ?? false
    aiTorchIndex.value = data.torch_index ?? 'cpu'
    aiDriverVersion.value = data.device?.driver_version ?? null
    aiEnvLoading.value = false
    writeAiCache({
      aiEnvReady: data.ai_env_ready,
      llamaReady: data.llama_ready ?? false,
      torchIndex: data.torch_index ?? 'cpu',
      driverVersion: data.device?.driver_version ?? null,
    })
  } catch (e) {
    console.error('Failed to load AI env status', e)
    if (!cache) aiEnvLoading.value = false
  }
}

async function installAiEnv() {
  aiInstalling.value = true
  try {
    const res = await apiFetch('/setup/initialize', { method: 'POST' })
    if (!res.ok) { aiInstalling.value = false; return }
    const { task_id } = await res.json()
    aiInstallTaskId.value = task_id
    taskStore.addTask({
      taskId: task_id,
      taskType: 'ai.setup',
      status: 'pending',
      progress: 0,
      message: '準備安裝...',
      result: null,
      error: null,
      label: '安裝 AI 推理環境',
      createdAt: new Date(),
      updatedAt: new Date(),
    })
  } catch {
    aiInstalling.value = false
  }
}

watch(
  () => aiInstallTask.value?.status,
  (status) => {
    if (status === 'completed' || status === 'failed') {
      aiInstallTaskId.value = null
      aiInstalling.value = false
      if (status === 'completed') {
        aiInstalled.value = true
        aiEnvReady.value = true
        llamaReady.value = true
        writeAiCache({ aiEnvReady: true, llamaReady: true, torchIndex: aiTorchIndex.value, driverVersion: aiDriverVersion.value })
      }
    }
  },
)

const coreModules = computed(() => {
  const tag = aiTorchIndex.value === 'cpu' ? 'CPU' : aiTorchIndex.value.toUpperCase()
  return [
    { key: 'torch',   icon: 'bi-lightning-charge', name: 'PyTorch',          tag,   desc: '深度學習推理框架',     ready: aiEnvReady.value },
    { key: 'whisper', icon: 'bi-mic',              name: 'faster-whisper',   tag: '', desc: '語音辨識引擎',        ready: aiEnvReady.value },
    { key: 'llama',   icon: 'bi-translate',        name: 'llama-cpp-python', tag,   desc: '翻譯推理引擎（GGUF）', ready: llamaReady.value },
    { key: 'hf',      icon: 'bi-cloud-download',   name: 'huggingface-hub',  tag: '', desc: 'AI 模型下載管理',     ready: aiEnvReady.value },
  ]
})

// ── 模型管理 ──────────────────────────────────────────────────

interface ToolItem {
  id: string
  label: string
  description: string
  installed: boolean
  size_mb: number
}

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
const downloadProgress = ref<Record<string, number>>({})

// 用 polling 追蹤下載進度，避免多個 SSE 連線佔用 HTTP 連線上限
const _pollers = new Map<string, ReturnType<typeof setInterval>>()

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

  // 直接加入 store（不開 SSE），改用 polling 避免佔用 HTTP 連線
  taskStore.tasks.set(task_id, {
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

  async function doPoll() {
    try {
      const pollRes = await apiFetch(`/tasks/${task_id}`)
      if (!pollRes.ok) return
      const data = await pollRes.json()
      const task = taskStore.tasks.get(task_id)
      if (!task) { clearInterval(poller); _pollers.delete(id); return }
      const isDone = data.status === 'completed' || data.status === 'failed'
      const progress = data.progress ?? task.progress
      // 直接更新 prop 觸發子元件 re-render（比跨元件 task store tracking 更可靠）
      downloadProgress.value[id] = progress
      // 更新 store 供 watch 偵測完成狀態
      task.progress = progress
      task.status = isDone ? data.status : 'processing'
      task.updatedAt = new Date()
      if (isDone) {
        clearInterval(poller)
        _pollers.delete(id)
      }
    } catch { /* ignore network errors, retry next interval */ }
  }

  // 立即打一次（後端 handler 在 submit 後幾毫秒內就會 emit 0.05），
  // 之後每 1500ms 一次
  setTimeout(doPoll, 300)
  const poller = setInterval(doPoll, 1500)
  _pollers.set(id, poller)
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

// 監聽任務狀態 → 清理 downloadingTaskId 並更新 downloaded 旗標
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

onUnmounted(() => {
  for (const poller of _pollers.values()) clearInterval(poller)
})

function restartApp() {
  ;(window as any).electron?.restart()
}

onMounted(() => {
  loadAiEnvStatus()
  loadModelStatus()
})
</script>

<template>
  <!-- 核心模組 -->
  <h6 class="section-title">核心模組</h6>

  <div class="module-list">
    <div class="module-item" v-for="mod in coreModules" :key="mod.key">
      <div class="module-info">
        <span class="module-label">{{ mod.desc }}</span>
        <span class="module-sub">{{ mod.name }}<template v-if="mod.tag"> ({{ mod.tag.toLowerCase() }})</template></span>
      </div>
      <span v-if="aiEnvLoading" class="module-badge badge-loading">
        <i class="bi bi-three-dots"></i>
      </span>
      <span v-else class="module-badge" :class="mod.ready ? 'badge-ok' : 'badge-off'">
        <i class="bi" :class="mod.ready ? 'bi-check-circle-fill' : 'bi-x-circle-fill'"></i>
        {{ mod.ready ? '已安裝' : '未安裝' }}
      </span>
    </div>
  </div>

  <!-- 安裝進行中 -->
  <div v-if="!aiEnvLoading && aiInstallTask" class="ai-env-card ai-env-installing">
    <div class="ai-env-body">
      <span class="ai-env-name">{{ aiInstallTask.message }}</span>
      <div class="cuda-progress-row">
        <div class="download-progress cuda-progress-bar">
          <div class="progress-bar" :style="{ width: `${(aiInstallTask.progress * 100).toFixed(0)}%` }"></div>
        </div>
        <span class="progress-label">{{ (aiInstallTask.progress * 100).toFixed(0) }}%</span>
      </div>
    </div>
  </div>

  <!-- 安裝完成，需重啟 -->
  <div v-else-if="!aiEnvLoading && aiInstalled" class="ai-env-card ai-env-ok">
    <i class="bi bi-check-circle-fill"></i>
    <div class="ai-env-body">
      <span class="ai-env-name">安裝完成</span>
      <span class="ai-env-hint">請重新啟動應用程式以套用</span>
      <button class="cuda-restart-btn" @click="restartApp()">
        <i class="bi bi-arrow-counterclockwise"></i> 立即重啟
      </button>
    </div>
  </div>

  <!-- 有模組未啟用 → 安裝按鈕 -->
  <div v-else-if="!aiEnvLoading && (!aiEnvReady || !llamaReady)" class="ai-env-card ai-env-warn">
    <i class="bi bi-exclamation-triangle-fill"></i>
    <div class="ai-env-body">
      <span class="ai-env-name">核心模組未完整安裝</span>
      <span class="ai-env-hint">
        將安裝 <strong>Torch {{ aiTorchIndex.toUpperCase() }}</strong> + llama-cpp-python
        <template v-if="aiDriverVersion">（驅動 {{ aiDriverVersion }}）</template>
        <template v-else>（CPU 模式）</template>
      </span>
      <button class="cuda-download-btn" :disabled="aiInstalling" @click="installAiEnv">
        <i class="bi bi-download"></i> 安裝核心模組
      </button>
    </div>
  </div>

  <!-- 模型與工具下載 -->
  <h6 class="section-title mt">模型與工具</h6>

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

    <button class="refresh-btn" @click="loadModelStatus">
      <i class="bi bi-arrow-clockwise"></i> 重新整理
    </button>
  </template>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
// 核心模組列表
.module-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.module-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
}

.module-info {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  flex: 1;
  min-width: 0;
}

.module-label {
  font-size: 0.875rem;
  color: var(--text-primary);
  font-weight: 500;
}

.module-sub {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.module-badge {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  font-weight: 500;
  padding: 0.2rem 0.6rem;
  border-radius: 20px;
  flex-shrink: 0;

  &.badge-ok  { background: rgba(16, 185, 129, 0.12); color: #10b981; }
  &.badge-off { background: rgba(239, 68, 68, 0.1);   color: #f87171; }
  &.badge-loading { background: transparent; color: var(--text-muted); }

  i { font-size: 0.72rem; }
}

// AI 推理環境 card
.ai-env-card {
  display: flex;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid;
  margin-top: 0.75rem;

  > i { font-size: 1.25rem; flex-shrink: 0; margin-top: 0.1rem; }

  &.ai-env-ok      { background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.25); > i { color: #10b981; } }
  &.ai-env-warn    { background: rgba(245, 158, 11, 0.08);  border-color: rgba(245, 158, 11, 0.25);  > i { color: #f59e0b; } }
  &.ai-env-installing { background: var(--input-bg); border-color: var(--input-border); }
}

.ai-env-body {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  flex: 1;
}

.ai-env-name { color: var(--text-primary); font-size: 0.875rem; font-weight: 500; }

.ai-env-hint {
  color: var(--text-muted);
  font-size: 0.75rem;
  strong { color: var(--text-secondary); }
}

.cuda-progress-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.cuda-progress-bar { width: 200px; }

.download-progress {
  background: var(--input-bg);
  border-radius: 4px;
  overflow: hidden;
  height: 4px;
  flex: 1;
}

.progress-bar {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.progress-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  min-width: 40px;
  text-align: right;
}

.cuda-download-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.5rem;
  padding: 0.5rem 1rem;
  background: linear-gradient(135deg, var(--color-info) 0%, var(--color-primary) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  width: fit-content;

  &:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(96, 165, 250, 0.3); }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

.cuda-restart-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.25rem;
  padding: 0.4rem 0.875rem;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: 8px;
  color: #10b981;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  width: fit-content;
  &:hover { background: rgba(16, 185, 129, 0.2); }
}

// 模型列表
.models-loading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 1rem;
  padding: 0.4rem 0.875rem;
  background: transparent;
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s ease;
  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
}
</style>
