<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useTheme, type ThemeMode } from '../composables/useTheme'
import { useSettingsStore } from '@/stores/settings'
import { useTaskStore } from '@/stores/tasks'
import AppSelect from '@/components/common/AppSelect.vue'
import type { Task } from '@/types/task'

const { themeMode, setTheme } = useTheme()
const settingsStore = useSettingsStore()
const taskStore = useTaskStore()

// 當前選中的區塊
const activeSection = ref<'general' | 'gpu' | 'models' | 'about'>('general')

const sections = [
  { id: 'general' as const, icon: 'bi-sliders', label: '一般' },
  { id: 'gpu' as const, icon: 'bi-gpu-card', label: '硬體加速' },
  { id: 'models' as const, icon: 'bi-download', label: '模型管理' },
  { id: 'about' as const, icon: 'bi-info-circle', label: '關於' },
]

// 一般設定
const settings = ref({
  theme: 'system' as ThemeMode,
  language: 'zh-TW',
  outputDir: '',
  tempDir: '',
  autoCleanTemp: true,
})

const themes = [
  { value: 'system', label: '跟隨系統' },
  { value: 'dark', label: '深色' },
  { value: 'light', label: '淺色' },
]

const languages = [
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en', label: 'English' },
]

// 硬體加速
const gpuEnabled = ref(false)
const gpuDetecting = ref(false)

// CUDA DLL 下載
const cudaDownloadTaskId = ref<string | null>(null)
const cudaSubmitting = ref(false)
const cudaDownloadTask = computed(() => {
  if (!cudaDownloadTaskId.value) return null
  return taskStore.tasks.get(cudaDownloadTaskId.value) ?? null
})

// 載入設定
onMounted(() => {
  const saved = localStorage.getItem('app-settings')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      settings.value = { ...settings.value, ...parsed }
      if (parsed.gpuEnabled !== undefined) {
        gpuEnabled.value = parsed.gpuEnabled
      }
    } catch {
      // ignore
    }
  }
  // 同步主題
  settings.value.theme = themeMode.value

  // 如果 GPU 已啟用，自動偵測
  if (gpuEnabled.value) {
    detectGpu()
  }
})

// 即時套用主題
watch(() => settings.value.theme, (newTheme) => {
  setTheme(newTheme)
})

// 自動儲存一般設定
watch(settings, () => {
  saveSettings()
}, { deep: true })

// GPU 啟用切換
watch(gpuEnabled, (val) => {
  saveSettings()
  if (val) {
    detectGpu()
  }
})

function saveSettings() {
  const data = {
    ...settings.value,
    gpuEnabled: gpuEnabled.value,
  }
  localStorage.setItem('app-settings', JSON.stringify(data))
}

async function detectGpu() {
  gpuDetecting.value = true
  await settingsStore.loadDeviceInfo()
  gpuDetecting.value = false
}

async function downloadCuda() {
  cudaSubmitting.value = true
  try {
    const res = await fetch('/api/setup/cuda/download', { method: 'POST' })
    if (!res.ok) {
      console.error('CUDA download request failed:', res.statusText)
      return
    }
    const { task_id } = await res.json()
    cudaDownloadTaskId.value = task_id
    taskStore.addTask({
      taskId: task_id,
      taskType: 'setup.cuda_download',
      status: 'pending',
      progress: 0,
      message: '準備下載 CUDA DLL...',
      result: null,
      error: null,
      label: '安裝 CUDA 加速',
      createdAt: new Date(),
      updatedAt: new Date(),
    })
  } finally {
    cudaSubmitting.value = false
  }
}

// CUDA 下載完成後提示重啟
const cudaInstalled = ref(false)

watch(cudaDownloadTask, (task) => {
  if (task && (task.status === 'completed' || task.status === 'failed')) {
    cudaDownloadTaskId.value = null
    if (task.status === 'completed') {
      cudaInstalled.value = true
    }
  }
})

// ── 模型管理 ──────────────────────────────────────────────────────────────────

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
}

interface ModelsStatus {
  tools: ToolItem[]
  models: ModelItem[]
}

const modelStatus = ref<ModelsStatus | null>(null)
const modelStatusLoading = ref(false)
// itemId → taskId
const downloadingTaskId = ref<Record<string, string>>({})

async function loadModelStatus() {
  modelStatusLoading.value = true
  try {
    const res = await fetch('/api/setup/models')
    if (res.ok) {
      modelStatus.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load model status', e)
  } finally {
    modelStatusLoading.value = false
  }
}

async function downloadItem(id: string) {
  const res = await fetch('/api/setup/models/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (!res.ok) {
    console.error('Download request failed:', res.statusText)
    return
  }
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

function getDownloadingTask(id: string): Task | undefined {
  const taskId = downloadingTaskId.value[id]
  if (!taskId) return undefined
  return taskStore.tasks.get(taskId)
}

// 監聽任務完成 → 刷新狀態
watch(
  () => taskStore.allTasks.map((t) => t.status),
  () => {
    for (const [itemId, taskId] of Object.entries(downloadingTaskId.value)) {
      const task = taskStore.tasks.get(taskId)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        delete downloadingTaskId.value[itemId]
        loadModelStatus()
      }
    }
  },
)

// 切到模型管理 tab 時才 lazy load
watch(activeSection, (val) => {
  if (val === 'models' && !modelStatus.value) {
    loadModelStatus()
  }
})

function formatSize(mb: number): string {
  if (mb >= 1000) return `${(mb / 1000).toFixed(1)} GB`
  return `${mb} MB`
}

async function selectOutputDir() {
  if (window.electron?.selectFolder) {
    const result = await window.electron.selectFolder()
    if (result) {
      settings.value.outputDir = result
    }
  }
}

async function selectTempDir() {
  if (window.electron?.selectFolder) {
    const result = await window.electron.selectFolder()
    if (result) {
      settings.value.tempDir = result
    }
  }
}

// GPU 顯示 VRAM
function formatVram(bytes: number | null): string {
  if (!bytes) return ''
  const gb = bytes / (1024 * 1024 * 1024)
  return `${gb.toFixed(1)} GB`
}
</script>

<template>
  <div class="settings-layout">
    <!-- 左側 sidebar -->
    <aside class="settings-sidebar">
      <div class="sidebar-list">
        <button
          v-for="s in sections"
          :key="s.id"
          class="sidebar-item"
          :class="{ active: activeSection === s.id }"
          @click="activeSection = s.id"
        >
          <i :class="['bi', s.icon]"></i>
          <span>{{ s.label }}</span>
        </button>
      </div>
    </aside>

    <!-- 右側 content -->
    <main class="settings-content">
      <!-- 一般 -->
      <div v-if="activeSection === 'general'" class="section-content">
        <h6 class="section-title">外觀</h6>

        <div class="setting-item">
          <label>主題</label>
          <AppSelect v-model="settings.theme" :options="themes" size="sm" />
        </div>

        <div class="setting-item">
          <label>語言</label>
          <AppSelect v-model="settings.language" :options="languages" size="sm" />
        </div>

        <h6 class="section-title mt">檔案路徑</h6>

        <div class="setting-item">
          <label>預設輸出資料夾</label>
          <div class="path-input">
            <input
              type="text"
              v-model="settings.outputDir"
              class="form-control"
              placeholder="使用原檔案所在資料夾"
              readonly
            />
            <button class="browse-btn" @click="selectOutputDir">
              <i class="bi bi-folder2-open"></i>
            </button>
          </div>
        </div>

        <div class="setting-item">
          <label>暫存資料夾</label>
          <div class="path-input">
            <input
              type="text"
              v-model="settings.tempDir"
              class="form-control"
              placeholder="使用系統預設"
              readonly
            />
            <button class="browse-btn" @click="selectTempDir">
              <i class="bi bi-folder2-open"></i>
            </button>
          </div>
        </div>

        <div class="setting-item checkbox-item">
          <label class="checkbox-label" @click="settings.autoCleanTemp = !settings.autoCleanTemp">
            <span class="checkbox" :class="{ checked: settings.autoCleanTemp }">
              <i v-if="settings.autoCleanTemp" class="bi bi-check"></i>
            </span>
            <span>關閉時自動清理暫存檔</span>
          </label>
        </div>
      </div>

      <!-- 硬體加速 -->
      <div v-if="activeSection === 'gpu'" class="section-content">
        <h6 class="section-title">GPU 加速</h6>

        <div class="setting-item checkbox-item">
          <label class="checkbox-label" @click="gpuEnabled = !gpuEnabled">
            <span class="checkbox" :class="{ checked: gpuEnabled }">
              <i v-if="gpuEnabled" class="bi bi-check"></i>
            </span>
            <span>啟用 GPU 加速</span>
          </label>
          <p class="setting-desc">使用 GPU 加速語音辨識與翻譯模型推理</p>
        </div>

        <!-- GPU 偵測結果 -->
        <div v-if="gpuEnabled" class="gpu-status">
          <!-- 偵測中 -->
          <div v-if="gpuDetecting" class="gpu-detecting">
            <div class="spinner"></div>
            <span>偵測硬體中...</span>
          </div>

          <!-- 偵測完成 -->
          <template v-else-if="settingsStore.deviceInfo">
            <!-- 有 NVIDIA GPU + 有 CUDA -->
            <div v-if="settingsStore.hasGPU" class="gpu-result gpu-ok">
              <i class="bi bi-check-circle-fill"></i>
              <div class="gpu-info">
                <span class="gpu-name">{{ settingsStore.deviceInfo.device_name }}</span>
                <span class="gpu-detail">
                  VRAM: {{ formatVram(settingsStore.deviceInfo.memory_total) }}
                  <template v-if="settingsStore.deviceInfo.memory_free">
                    （可用: {{ formatVram(settingsStore.deviceInfo.memory_free) }}）
                  </template>
                </span>
                <span class="gpu-label">GPU 加速已啟用</span>
              </div>
            </div>

            <!-- 有 NVIDIA GPU + 無 CUDA DLL -->
            <div v-else-if="settingsStore.needsCudaToolkit" class="gpu-result gpu-warn">
              <i class="bi bi-exclamation-triangle-fill"></i>
              <div class="gpu-info">
                <span class="gpu-name">{{ settingsStore.deviceInfo.device_name }}</span>
                <span class="gpu-detail">偵測到 NVIDIA GPU，但尚未安裝 CUDA DLL</span>
                <span class="gpu-hint">下載 CUDA DLL（約 850 MB）即可啟用 GPU 加速，資料存於 AppData 並跨版本保留</span>
                <!-- 下載進行中 -->
                <template v-if="cudaDownloadTask">
                  <div class="cuda-progress-row">
                    <div class="download-progress cuda-progress-bar">
                      <div
                        class="progress-bar"
                        :style="{ width: `${(cudaDownloadTask.progress * 100).toFixed(0)}%` }"
                      ></div>
                    </div>
                    <span class="progress-label">{{ (cudaDownloadTask.progress * 100).toFixed(0) }}%</span>
                  </div>
                  <span class="cuda-progress-msg">{{ cudaDownloadTask.message }}</span>
                </template>
                <!-- 安裝完成 → 提示重啟 -->
                <div v-else-if="cudaInstalled" class="cuda-restart-hint">
                  <i class="bi bi-check-circle-fill" style="color: #10b981"></i>
                  <span>安裝完成，請重新啟動應用程式以啟用 GPU 加速</span>
                  <button class="cuda-restart-btn" @click="window.electron?.restart()">
                    <i class="bi bi-arrow-counterclockwise"></i> 立即重啟
                  </button>
                </div>
                <!-- 下載按鈕 -->
                <button
                  v-else
                  class="cuda-download-btn"
                  :disabled="cudaSubmitting"
                  @click="downloadCuda"
                >
                  <i class="bi bi-download"></i>
                  安裝 CUDA 加速
                </button>
              </div>
            </div>

            <!-- 無 GPU -->
            <div v-else class="gpu-result gpu-none">
              <i class="bi bi-cpu"></i>
              <div class="gpu-info">
                <span class="gpu-name">未偵測到支援的 GPU</span>
                <span class="gpu-detail">將使用 CPU 模式運行，速度較慢</span>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 模型管理 -->
      <div v-if="activeSection === 'models'" class="section-content models-section">
        <div v-if="modelStatusLoading" class="models-loading">
          <div class="spinner"></div>
          <span>載入中...</span>
        </div>

        <template v-else-if="modelStatus">
          <!-- 超解析工具 -->
          <h6 class="section-title">超解析工具</h6>
          <div class="model-list">
            <div v-for="tool in modelStatus.tools" :key="tool.id" class="model-item">
              <div class="model-info">
                <span class="model-label">{{ tool.label }}</span>
                <span class="model-desc">{{ tool.description }}</span>
              </div>
              <span class="model-size">{{ formatSize(tool.size_mb) }}</span>
              <div class="model-action">
                <template v-if="getDownloadingTask(tool.id)">
                  <div class="download-progress">
                    <div
                      class="progress-bar"
                      :style="{ width: `${(getDownloadingTask(tool.id)!.progress * 100).toFixed(0)}%` }"
                    ></div>
                  </div>
                  <span class="progress-label">
                    {{ (getDownloadingTask(tool.id)!.progress * 100).toFixed(0) }}%
                  </span>
                </template>
                <span v-else-if="tool.installed" class="status-badge installed">
                  <i class="bi bi-check-circle-fill"></i> 已安裝
                </span>
                <button v-else class="download-btn" @click="downloadItem(tool.id)">
                  <i class="bi bi-download"></i> 安裝
                </button>
              </div>
            </div>
          </div>

          <!-- 語音識別 -->
          <h6 class="section-title mt">語音識別</h6>
          <div class="model-list">
            <div
              v-for="model in modelStatus.models.filter(m => m.category === 'stt')"
              :key="model.id"
              class="model-item"
            >
              <div class="model-info">
                <span class="model-label">{{ model.label }}</span>
              </div>
              <span class="model-size">{{ formatSize(model.size_mb) }}</span>
              <div class="model-action">
                <template v-if="getDownloadingTask(model.id)">
                  <div class="download-progress">
                    <div
                      class="progress-bar"
                      :style="{ width: `${(getDownloadingTask(model.id)!.progress * 100).toFixed(0)}%` }"
                    ></div>
                  </div>
                  <span class="progress-label">
                    {{ (getDownloadingTask(model.id)!.progress * 100).toFixed(0) }}%
                  </span>
                </template>
                <span v-else-if="model.downloaded" class="status-badge installed">
                  <i class="bi bi-check-circle-fill"></i> 已安裝
                </span>
                <button v-else class="download-btn" @click="downloadItem(model.id)">
                  <i class="bi bi-download"></i> 安裝
                </button>
              </div>
            </div>
          </div>

          <!-- 翻譯模型 -->
          <h6 class="section-title mt">翻譯模型</h6>
          <div class="model-list">
            <div
              v-for="model in modelStatus.models.filter(m => m.category === 'translate')"
              :key="model.id"
              class="model-item"
            >
              <div class="model-info">
                <span class="model-label">{{ model.label }}</span>
              </div>
              <span class="model-size">{{ formatSize(model.size_mb) }}</span>
              <div class="model-action">
                <template v-if="getDownloadingTask(model.id)">
                  <div class="download-progress">
                    <div
                      class="progress-bar"
                      :style="{ width: `${(getDownloadingTask(model.id)!.progress * 100).toFixed(0)}%` }"
                    ></div>
                  </div>
                  <span class="progress-label">
                    {{ (getDownloadingTask(model.id)!.progress * 100).toFixed(0) }}%
                  </span>
                </template>
                <span v-else-if="model.downloaded" class="status-badge installed">
                  <i class="bi bi-check-circle-fill"></i> 已安裝
                </span>
                <button v-else class="download-btn" @click="downloadItem(model.id)">
                  <i class="bi bi-download"></i> 安裝
                </button>
              </div>
            </div>
          </div>

          <button class="refresh-btn" @click="loadModelStatus">
            <i class="bi bi-arrow-clockwise"></i> 重新整理
          </button>
        </template>
      </div>

      <!-- 關於 -->
      <div v-if="activeSection === 'about'" class="section-content">
        <div class="about-section">
          <h4 class="about-name">MediaTranX</h4>
          <p class="about-version">版本 1.0.0</p>
          <p class="about-desc">
            本地 AI 驅動的多媒體處理工具，支援影片字幕提取、翻譯、音訊處理、圖片處理等功能。
          </p>
          <p class="about-desc">
            所有 AI 模型均在本機運行，無需上傳資料至雲端，保護您的隱私。
          </p>
        </div>
      </div>
    </main>
  </div>
</template>

<style lang="scss" scoped>
.settings-layout {
  display: flex;
  height: calc(100vh - 40px);
  gap: 1rem;
  padding: 1rem;
}

// 左側 sidebar
.settings-sidebar {
  width: 180px;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  padding: 1rem;
  padding-top: 0.5rem;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.sidebar-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sidebar-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.7rem 1rem;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;

  i {
    font-size: 1.1rem;
    width: 22px;
  }

  span {
    font-size: 0.9rem;
  }

  &:hover {
    color: var(--text-primary);
    background: var(--panel-bg);
  }

  &.active {
    color: var(--text-primary);
    background: var(--panel-bg);
  }
}

// 右側 content
.settings-content {
  flex: 1;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 1.5rem;
  overflow-y: auto;
}

.section-content {
  max-width: 560px;
  margin: 0 auto;
}

.section-title {
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 0.75rem;

  &.mt {
    margin-top: 1.5rem;
  }
}

.setting-item {
  margin-bottom: 1rem;

  &:last-child {
    margin-bottom: 0;
  }

  > label {
    display: block;
    color: var(--text-secondary);
    font-size: 0.9rem;
    margin-bottom: 0.5rem;
  }
}

.setting-desc {
  color: var(--text-muted);
  font-size: 0.8rem;
  margin: 0.25rem 0 0 0;
}

.form-control {
  width: 100%;
  padding: 0.375rem 0.625rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;

  &::placeholder {
    color: var(--text-muted);
  }

  &:focus {
    outline: none;
    border-color: var(--input-border-focus);
    background: var(--input-bg-focus);
  }
}

.path-input {
  display: flex;
  gap: 0.5rem;

  .form-control {
    flex: 1;
  }
}

.browse-btn {
  padding: 0.375rem 0.75rem;
  background: var(--panel-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }
}

.checkbox-item {
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.9rem;
    cursor: pointer;
    user-select: none;
  }
}

.checkbox {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: 1.5px solid var(--input-border);
  border-radius: 4px;
  background: var(--input-bg);
  transition: all 0.15s ease;
  flex-shrink: 0;

  i {
    font-size: 0.75rem;
    color: white;
  }

  &.checked {
    background: var(--color-primary);
    border-color: var(--color-primary);
  }
}

// GPU 區塊
.gpu-status {
  margin-top: 1rem;
}

.gpu-detecting {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--input-bg);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--panel-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.gpu-result {
  display: flex;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid;

  > i {
    font-size: 1.25rem;
    flex-shrink: 0;
    margin-top: 0.1rem;
  }

  &.gpu-ok {
    background: rgba(16, 185, 129, 0.08);
    border-color: rgba(16, 185, 129, 0.25);
    > i { color: #10b981; }
  }

  &.gpu-warn {
    background: rgba(245, 158, 11, 0.08);
    border-color: rgba(245, 158, 11, 0.25);
    > i { color: #f59e0b; }
  }

  &.gpu-none {
    background: var(--input-bg);
    border-color: var(--input-border);
    > i { color: var(--text-muted); }
  }
}

.gpu-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.gpu-name {
  color: var(--text-primary);
  font-size: 0.95rem;
  font-weight: 500;
}

.gpu-detail {
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.gpu-label {
  color: #10b981;
  font-size: 0.85rem;
  font-weight: 500;
}

.gpu-hint {
  color: var(--text-muted);
  font-size: 0.8rem;
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
  font-size: 0.85rem;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s ease;
  width: fit-content;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(96, 165, 250, 0.3);
    color: white;
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.cuda-restart-hint {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.5rem;
  font-size: 0.85rem;
  color: var(--text-secondary);

  i { flex-shrink: 0; }
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
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  width: fit-content;

  &:hover {
    background: rgba(16, 185, 129, 0.2);
  }
}

.cuda-progress-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.cuda-progress-bar {
  width: 200px;
}

.cuda-progress-msg {
  color: var(--text-muted);
  font-size: 0.78rem;
  margin-top: 0.25rem;
}

// 模型管理
.models-section {
  max-width: 640px;
}

.models-loading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

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
  font-size: 0.78rem;
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
  width: 130px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  position: relative;
  left: 2px;

  &.installed {
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
  font-size: 0.78rem;
  min-width: 32px;
  text-align: right;
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
  font-size: 0.82rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }
}

// 關於
.about-section {
  padding: 1rem 0;
}

.about-name {
  color: var(--text-primary);
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0 0 0.25rem 0;
}

.about-version {
  color: var(--text-muted);
  font-size: 0.9rem;
  margin: 0 0 1.25rem 0;
}

.about-desc {
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.6;
  margin: 0 0 0.75rem 0;

  &:last-child {
    margin-bottom: 0;
  }
}
</style>
